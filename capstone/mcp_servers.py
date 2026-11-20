"""Four typed FastMCP servers. No arbitrary URLs, paths, code or shell tools."""
import argparse
import asyncio
import os
from typing import Any
from pydantic import BaseModel, Field
from fastmcp import FastMCP, Client
import app
from . import retrieval, storage
from .security import TOOLS

class ToolResult(BaseModel):
    ok:bool=True
    data:dict[str,Any]=Field(default_factory=dict)
    error:str=''
    code:str=''

media=FastMCP('media-tools')
knowledge=FastMCP('knowledge-search')
validation=FastMCP('validation-engine')
actions=FastMCP('notes-actions')
READ={'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False}
WRITE={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}

@media.tool(annotations=READ)
def inspect_source(source_id:str)->ToolResult:
    """Read original media metadata and approved extraction, without performing analysis."""
    row=app.get_job(source_id)
    if not row or row['status']!='approved':return ToolResult(ok=False,error='Approved source not found.',code='NOT_FOUND')
    return ToolResult(data={'source':app.public_job(row)})

@knowledge.tool(annotations=READ)
def search_passages(query:str,category:str='all',collection_id:str='',after:float=0,before:float=0,
                    defenses:bool=True,modality:str='multimodal',rerank:bool=True)->ToolResult:
    """Retrieve approved source evidence with passage IDs and saved dates."""
    try:return ToolResult(data=retrieval.retrieve(query,category,collection_id,after,before,defenses=defenses,modality=modality,rerank=rerank))
    except ValueError:return ToolResult(ok=False,error='Retrieval failed.',code='RETRIEVAL_ERROR')

@knowledge.tool(annotations=READ)
def get_passage(passage_id:str)->ToolResult:
    """Read one evidence passage by stable identifier."""
    result=retrieval.get_passage(passage_id)
    return ToolResult(data={'passage':result}) if result else ToolResult(ok=False,error='Passage not found.',code='NOT_FOUND')

@validation.tool(annotations=READ)
def verify_claims(claims:list[dict[str,Any]],allowed:list[dict[str,Any]])->ToolResult:
    """Check citation membership and exact quote support; semantic entailment requires model review."""
    by_id={p['id']:p for p in allowed};good=[];issues=[]
    for i,claim in enumerate(claims[:20]):
        text=str(claim.get('text',''))[:1500].strip()
        refs=claim.get('passage_ids',[])
        if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in by_id for r in refs):
            issues.append({'claim':i,'reason':'Missing or unknown citation.'});continue
        refs=list(dict.fromkeys(refs))
        # Always preserve source metadata from retrieval, never from the model.
        good.append({'text':text,'citations':[by_id[r] for r in refs],
                     'verification':'exact_source_quote' if any(text==by_id[r]['text'] for r in refs) else 'citation_check_only'})
    return ToolResult(data={'claims':good,'issues':issues})

@actions.tool(annotations=WRITE)
def publish_note(run_id:str,payload:dict[str,Any],approval_hash:str)->ToolResult:
    """Write the exact approved answer to the local mock notebook. Requires graph-issued grant."""
    # The action server has a separate short-lived capability minted by the API
    # only after interrupt approval. A payload digest alone is not authority.
    from .grants import consume
    if not consume(run_id,payload,approval_hash):return ToolResult(ok=False,error='No valid approval grant.',code='APPROVAL_REQUIRED')
    try:return ToolResult(data=storage.publish(run_id,payload,approval_hash))
    except ValueError as ex:return ToolResult(ok=False,error=str(ex),code='STALE_APPROVAL')

SERVERS={'media':media,'knowledge':knowledge,'validation':validation,'actions':actions}
TOOLS_MAP={'search_passages':'knowledge','get_passage':'knowledge','verify_claims':'validation','publish_note':'actions'}

async def call_tool(name,args,budget,agent):
    budget.tool(agent,name,args)
    kind=TOOLS_MAP[name]
    # Remote read tools in Compose; write action stays in process so grants are
    # never sent over the network. The standalone write server is deny-by-default.
    target=os.environ.get('MCP_'+kind.upper()+'_URL') if kind!='actions' else None
    async with Client(target or SERVERS[kind]) as client:
        result=await client.call_tool(name,args)
        structured=result.structured_content
        if not structured:
            import json
            structured=json.loads(result.content[0].text)
    if 'result' in structured:structured=structured['result']
    if not structured.get('ok'):
        TOOLS.labels(agent,name,'error').inc()
        raise ValueError(structured.get('error','Tool failed.'))
    TOOLS.labels(agent,name,'ok').inc()
    return structured['data']


def invoke(name,args,budget,agent):return asyncio.run(call_tool(name,args,budget,agent))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('server',choices=SERVERS)
    parser.add_argument('--port',type=int,default=8901)
    opts=parser.parse_args()
    SERVERS[opts.server].run(transport='http',host='0.0.0.0',port=opts.port)
