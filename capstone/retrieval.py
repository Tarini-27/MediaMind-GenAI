"""Evidence passages with stable IDs, hybrid retrieval and optional cross-encoder."""
import hashlib
import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from rank_bm25 import BM25Okapi
from search_quality import query_terms, keyword_match, rerank_candidates
import app
from .security import INJECTION, scrub

_encoder=None
_encoder_lock=threading.Lock()

def seconds(stamp):
    if not isinstance(stamp,str) or not re.fullmatch(r'(?:\d+:)?\d{1,3}:[0-5]\d(?:\.\d+)?',stamp):return None
    parts=list(map(float,stamp.split(':')))
    return sum(x*60**i for i,x in enumerate(reversed(parts)))

def passages(category='all',collection_id='',after=0,before=0,defenses=True,modality='multimodal'):
    with app.conn() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM jobs WHERE status='approved' ORDER BY created DESC")]
        ids={x[0] for x in c.execute('SELECT job_id FROM collection_items WHERE collection_id=?',(collection_id,))} if collection_id else None
    result=[]
    for row in rows:
        if ids is not None and row['id'] not in ids:continue
        if after and row['created']<after or before and row['created']>before:continue
        note=app.normalise_note(json.loads(row['recipe']))
        topic=row.get('topic') if row.get('topic') in app.TOPICS else note['category']
        if category in app.TOPICS and topic!=category:continue
        for e in note.get('evidence',[]):
            linked=[]
            for field in ('key_points','steps','ingredients'):
                for item in note.get(field,[]):
                    if e['id'] in item.get('evidence_ids',[]):
                        linked.append(item.get('text') or (item.get('name','')+' '+item.get('quantity','')))

            if modality=='transcript' and e['kind'] not in ('spoken','provided_text'):continue
            if defenses and INJECTION.search(e['quote']):continue
            pid=row['id']+':'+e['id']
            result.append({'id':pid,'source_id':row['id'],'title':scrub(note['title']),
                'text':scrub(e['quote']),'kind':e['kind'],'timestamp':e.get('timestamp',''),
                'seconds':seconds(e.get('timestamp','')),'timestamp_quality':'approximate_model_report' if e.get('timestamp') else 'not_available',
                'category':topic,'saved_at':datetime.fromtimestamp(row['created'],timezone.utc).isoformat(),
                'source_version':hashlib.sha256(row['recipe'].encode()).hexdigest(),
                'media_url':'/media/'+row['id'] if row['media_path'] else '',
                '_embedding':row.get('embedding'),'_context':scrub(' '.join(linked))})
    return result


def get_passage(passage_id,defenses=True):
    return next(({k:v for k,v in p.items() if not k.startswith('_')} for p in passages(defenses=defenses) if p['id']==passage_id),None)


def retrieve(query,category='all',collection_id='',after=0,before=0,key='',semantic=False,
             rerank=True,defenses=True,modality='multimodal',limit=8,relevance_checker=None,model=None):
    docs=passages(category,collection_id,after,before,defenses,modality)
    # Equipment claims require explicit reviewed source support, as in the
    # original search flow; absence of an oven statement is not a no-oven match.
    if re.search(r'\b(no oven|without (?:an? )?oven|doesn.t (?:need|require) (?:an? )?oven)\b',query.lower()):
        allowed=set()
        with app.conn() as c:
            for row in c.execute("SELECT id,recipe FROM jobs WHERE status='approved'"):
                note=json.loads(row['recipe'])
                if note.get('oven_requirement')=='not_required' and note.get('oven_evidence_ids'):allowed.add(row['id'])
        docs=[p for p in docs if p['source_id'] in allowed]
    if not docs:return {'passages':[],'warnings':['No approved evidence passages match these filters.'],'mode':'BM25'}
    search_query=re.sub(r'\b(no oven|without (?:an? )?oven|doesn.t (?:need|require) (?:an? )?oven)\b',' ',query,flags=re.I)
    qt=query_terms(search_query,app.tokens)
    terms=[app.tokens(p['title']+' '+p['text']+' '+p['_context']+' '+p['category']) for p in docs]
    source_terms={}
    for p,t in zip(docs,terms):source_terms.setdefault(p['source_id'],set()).update(t)
    allowed={sid for sid,t in source_terms.items() if keyword_match(query,qt,t)}
    filter_only=not qt and search_query.strip()!=query.strip()
    if filter_only:allowed=set(source_terms)
    scores=BM25Okapi(terms,epsilon=.25).get_scores(qt)
    # BM25Okapi's IDF may be zero/negative for tiny all-overlap corpora. Positive
    # overlap is the candidate gate; RRF remains rank based in every corpus size.
    lexical=sorted((i for i,t in enumerate(terms) if docs[i]['source_id'] in allowed and (set(t)&set(qt) or filter_only)),key=lambda i:(scores[i],len(set(qt)&set(terms[i]))),reverse=True)
    ranks=[lexical];warnings=[]
    if semantic:
        if key:
            v=app.embed(query,key,query=True)
            try:
                from .vector_store import rank
                ranks.append(rank(v,docs))
            except (ImportError,ValueError,OSError,RuntimeError):
                similarities={i:app.cosine(v,json.loads(p['_embedding'])) for i,p in enumerate(docs) if p['_embedding']}
                ranks.append(sorted(similarities,key=similarities.get,reverse=True))
                warnings.append('Qdrant unavailable; used SQLite-backed vector scan.')
            if not any(p['_embedding'] for p in docs):warnings.append('Build semantic indexes on reviewed sources first. Using keyword retrieval.')
        else:warnings.append('Semantic retrieval needs a Gemini embedding key; using keyword retrieval.')
    fused={}
    for rank in ranks:
        for position,i in enumerate(rank):fused[i]=fused.get(i,0)+1/(61+position)
    selected=sorted(fused,key=fused.get,reverse=True)[:24]
    semantic_active=len(ranks)>1 and bool(ranks[-1])
    mode='BM25 + vectors / RRF' if semantic_active else 'BM25'
    if semantic_active:
        try:
            checker=relevance_checker or app.semantic_matches
            matches=checker(query,[(str(i),docs[i]['title']+' '+docs[i]['text']+' '+docs[i]['_context']) for i in selected],key,model)
            accepted=set(matches)
            selected=[i for i in selected if str(i) in accepted]
            mode+=' + meaning-based relevance check'
        except ValueError as ex:
            selected=[i for i in selected if i in lexical]
            warnings.append(str(ex)+' Used keyword matches only.')
            mode='BM25 (semantic relevance check unavailable)'
    # The small local cross-encoder orders already-validated results. It must not
    # veto a broader concept merely because its own short-query score is low.
    if rerank and selected:
        judged,warning=rerank_candidates(query,[(i,docs[i]['title']+' '+docs[i]['text']+' '+docs[i]['_context']) for i in selected])
        if judged is not None:
            checked=[i for i,_ in judged]
            selected=checked+[i for i in selected if i not in checked]
            mode+=' + cross-encoder reranking'
        elif warning:
            warnings.append('Local reranker unavailable; retained validated retrieval order.')
    results=[]
    for i in selected[:max(1,min(limit,20))]:
        p={k:v for k,v in docs[i].items() if not k.startswith('_')}
        p['score']=round(fused[i],6);results.append(p)
    return {'passages':results,'warnings':warnings,'mode':mode}
