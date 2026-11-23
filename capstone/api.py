"""FastAPI entry point. Reuses the existing tested import/review services."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import re
import threading
import time
import uuid
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.concurrency import run_in_threadpool
import app as legacy
from . import storage
from .graph import run_events, context, get_graph, close_graph
from .security import REQUESTS, LATENCY, scrub

_locks={}
_locks_guard=threading.Lock()

@asynccontextmanager
async def lifespan(application):
    legacy.init();storage.init();get_graph()
    legacy.STOP.clear()
    thread=threading.Thread(target=legacy.worker,daemon=True);thread.start()
    try:
        yield
    finally:
        legacy.STOP.set()
        thread.join(timeout=1)
        close_graph()

api=FastAPI(title='Gather Saved',version='0.3',lifespan=lifespan)

@api.middleware('http')
async def local_controls(request:Request,call_next):
    host=request.url.hostname
    if host not in {'localhost','127.0.0.1','testserver','api'}:
        return JSONResponse({'error':'Local workspace only.'},403)
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        return JSONResponse({'error':'Cross-origin requests are not allowed.'},403)
    if request.method=='POST':
        if request.headers.get('x-app-request')!='1':return JSONResponse({'error':'Missing application request header.'},403)
        if 'application/json' not in request.headers.get('content-type',''):return JSONResponse({'error':'Expected JSON.'},415)
        size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>22*1024*1024:return JSONResponse({'error':'Request too large.'},413)
            # Body is bounded before parsing or buffering the complete upload.
            if size==len(chunk):body=bytearray()
            body.extend(chunk)
        request._body=bytes(body) if size else b''
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store',
        'Content-Security-Policy':"default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
    return response

@api.exception_handler(ValueError)
async def bad_request(request,exc):return JSONResponse({'error':str(exc)[:500]},400)


def bridge(path,payload=None,headers=None):
    handler=legacy.Handler.__new__(legacy.Handler)
    handler.send_json=lambda data,status=200:JSONResponse(data,status)
    handler.local_request=lambda:True
    handler.path=path;handler.headers=headers or {}
    handler.serve_file=lambda path,mime,ranges=False:FileResponse(path,media_type=mime) if path.is_file() else JSONResponse({'error':'File not found.'},404)
    return handler.do_GET() if payload is None else handler.dispatch_post(path,payload)

@api.get('/health')
def health():return {'status':'ok','version':'0.3','agents':'langgraph','mcp_servers':4}

@api.get('/metrics')
def metrics():return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

@api.get('/api/memory')
def read_memory():return {'preferences':storage.memory()}

@api.post('/api/memory')
def write_memory(d:dict):
    if d.get('action')=='delete':
        storage.delete_memory()
        get_graph().store.delete(('local','preferences'),'current')
        return {'preferences':{}}
    return {'preferences':storage.set_memory(d.get('key'),d.get('value'),d.get('consent') is True)}

@api.get('/api/notebook')
def notebook():return {'notes':storage.notebook()}

@api.post('/api/notebook/delete')
def delete_note(d:dict):
    with legacy.conn() as c:c.execute('DELETE FROM notebooks WHERE id=?',(str(d.get('id','')),))
    return {'deleted':True}

@api.post('/api/chat/delete')
def delete_chat(d:dict):
    ident=str(d.get('run_id',''))
    if not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('Invalid chat ID.')
    with _locks_guard:lock=_locks.setdefault(ident,threading.Lock())
    if not lock.acquire(blocking=False):raise ValueError('Wait for this chat to finish.')
    try:get_graph().checkpointer.delete_thread(ident)
    finally:lock.release()
    return {'deleted':True}

@api.get('/api/chat/{run_id}')
def read_chat(run_id:str):
    if not re.fullmatch(r'[a-f0-9]{32}',run_id):raise ValueError('Invalid chat ID.')
    snapshot=get_graph().get_state({'configurable':{'thread_id':run_id}})
    return {'answer':snapshot.values.get('answer',{}),
            'approval':snapshot.interrupts[0].value if snapshot.interrupts else None}

@api.post('/api/chat')
async def chat(d:dict):
    ident=str(d.get('run_id') or uuid.uuid4().hex)
    if not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('Invalid chat ID.')
    question=str(d.get('question','')).strip()[:1000]
    resume=d.get('resume')
    if resume is not None and not isinstance(resume,dict):raise ValueError('Invalid approval response.')
    if resume is None and not question:raise ValueError('Enter a question.')
    filters=d.get('filters') or {}
    if not isinstance(filters,dict):raise ValueError('Invalid filters.')
    for field in ('after','before'):
        try:filters[field]=max(0,float(filters.get(field,0)))
        except (ValueError,TypeError):raise ValueError('Invalid saved date.') from None
    provider=d.get('provider','gemini')
    if provider not in ('gemini','openrouter'):raise ValueError('Unsupported provider.')
    ctx=context(str(d.get('api_key',''))[:300],str(d.get('model',''))[:150],provider,
                memory_enabled=d.get('memory') is True,semantic=d.get('semantic') is True,
                embedding_key=(str(d.get('api_key',''))[:300] or os.environ.get('GEMINI_API_KEY','')) if provider=='gemini' else os.environ.get('GEMINI_API_KEY',''))
    with _locks_guard:lock=_locks.setdefault(ident,threading.Lock())
    if not lock.acquire(blocking=False):raise ValueError('This chat is already processing a request.')
    queue=asyncio.Queue()
    loop=asyncio.get_running_loop()
    def worker():
        started=time.monotonic()
        try:
            for item in run_events(ident,question,ctx,resume=resume,filters=filters,save_requested=d.get('save_requested') is True,mode='team'):
                loop.call_soon_threadsafe(queue.put_nowait,item)
            REQUESTS.labels('success').inc()
        except Exception as ex:
            REQUESTS.labels('error').inc()
            message=str(ex) if isinstance(ex,ValueError) else 'The agent run failed. Your saved originals are safe. Please retry.'
            loop.call_soon_threadsafe(queue.put_nowait,{'type':'error','message':scrub(message)[:500],'run_id':ident})
        finally:
            LATENCY.observe(time.monotonic()-started)
            lock.release()
            loop.call_soon_threadsafe(queue.put_nowait,None)
    threading.Thread(target=worker,daemon=True).start()
    async def stream():
        yield 'data: '+json.dumps({'type':'started','run_id':ident})+'\n\n'
        while True:
            try:item=await asyncio.wait_for(queue.get(),timeout=15)
            except asyncio.TimeoutError:
                yield ': waiting\n\n';continue
            if item is None:break
            yield 'data: '+json.dumps(scrub(item),ensure_ascii=False)+'\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

@api.post('/api/{path:path}')
async def old_post(path:str,request:Request):
    try:payload=await request.json()
    except (ValueError,TypeError):raise ValueError('Expected valid JSON.') from None
    if not isinstance(payload,dict):raise ValueError('Expected a JSON object.')
    return await run_in_threadpool(bridge,'/api/'+path,payload)

@api.get('/{path:path}')
def old_get(path:str,request:Request):return bridge('/'+path,headers=dict(request.headers))
