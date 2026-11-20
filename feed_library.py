"""Local discovery feed. Browsing never creates saves, embeddings or model calls."""
import hashlib
import json
from pathlib import Path

def catalog(root, data, connection):
    preferred=Path(root)/'imports'/'reels-50'
    directory=preferred if (preferred/'sources.json').is_file() else Path(root)/'imports'/'reels-100'
    manifest=directory/'sources.json'
    result=[]
    if manifest.is_file():
        for item in json.loads(manifest.read_text()):
            media=(directory/item['relative_path']).resolve()
            poster=(directory/item.get('poster','')).resolve()
            if not media.is_relative_to(directory.resolve()) or not media.is_file():continue
            ident='f'+hashlib.sha256((item['provider']+':'+item['identifier']).encode()).hexdigest()[:31]
            result.append({'id':ident,'title':item['title'],'topic':item.get('display_topic') or item['topic'].replace('_',' ').title(),
                'duration':item['duration_seconds'],'mime':'video/mp4','created':0,
                'credit':('Original demo · English narration' if item.get('has_audio') else 'Original English-text demo') if item['provider']=='original_demo' else 'Creator video · source credited' if item['provider']=='archive' else 'Pexels discovery',
                'silent':not item.get('has_audio',False),'source_url':item['source_page'],'_media':media,
                '_poster':poster if poster.is_relative_to(directory.resolve()) and poster.is_file() else None})
    with connection() as c:
        uploads=[dict(r) for r in c.execute('SELECT * FROM feed_uploads ORDER BY created DESC')]
        saved={r['feed_id']:dict(r) for r in c.execute("SELECT id,feed_id,status,error,embedding FROM jobs WHERE feed_id<>''")}
    for r in reversed(uploads):
        media=(Path(data)/'media'/r['media_path']).resolve()
        if not media.is_relative_to((Path(data)/'media').resolve()) or not media.is_file():continue
        result.insert(0,{'id':r['id'],'title':r['title'],'topic':'Your uploads','duration':None,'mime':r['mime'],
            'created':r['created'],'credit':'Your upload','silent':False,'source_url':'','_media':media,'_poster':None})
    for r in result:
        job=saved.get(r['id']) or {}
        r.update(saved_id=job.get('id',''),status=job.get('status',''),error=job.get('error',''),
            search_ready=job.get('status')=='approved' and bool(job.get('embedding')),
            media_url='/feed-media/'+r['id'],poster_url='/feed-poster/'+r['id'] if r['_poster'] else '')
    return result

def public(item):
    return {k:v for k,v in item.items() if not k.startswith('_')}
