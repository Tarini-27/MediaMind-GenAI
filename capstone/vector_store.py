"""Qdrant note-vector adapter; SQLite remains the source of truth."""
import json
import os
import threading
import uuid
import app

_client=None
_path=None
_lock=threading.Lock()
COLLECTION='gather_notes_v1'

def client():
    global _client,_path
    location=os.environ.get('QDRANT_URL') or str(app.DATA/'vectors')
    with _lock:
        if _client is None or _path!=location:
            from qdrant_client import QdrantClient
            _client=QdrantClient(url=location,timeout=10) if location.startswith('http') else QdrantClient(path=location)
            _path=location
            if not _client.collection_exists(COLLECTION):
                from qdrant_client.models import VectorParams, Distance
                _client.create_collection(COLLECTION,vectors_config=VectorParams(size=768,distance=Distance.COSINE))
    return _client


def rank(query_vector,docs):
    from qdrant_client.models import PointStruct, Filter, HasIdCondition
    if len(query_vector)!=768:raise ValueError('Expected 768-dimensional query vector.')
    source_vectors={p['source_id']:json.loads(p['_embedding']) for p in docs if p.get('_embedding')}
    if not source_vectors:return []
    client()
    points=[];ids={}
    for source,vector in source_vectors.items():
        ident=str(uuid.UUID(source));ids[ident]=source
        points.append(PointStruct(id=ident,vector=vector))
    with _lock:
        db=client_unlocked()
        db.upsert(COLLECTION,points,wait=True)
        hits=db.query_points(COLLECTION,query=query_vector,query_filter=Filter(must=[HasIdCondition(has_id=list(ids))]),limit=len(ids)).points
    source_scores={ids[str(h.id)]:h.score for h in hits}
    # Scores are source-note vectors, not independently embedded video frames.
    return sorted((i for i,p in enumerate(docs) if p['source_id'] in source_scores),key=lambda i:source_scores[docs[i]['source_id']],reverse=True)


def client_unlocked():
    # Initialisation occurs before entering mutation locks.
    return _client


def delete(source_id):
    from qdrant_client.models import PointIdsList
    db=client()
    with _lock:db.delete(COLLECTION,points_selector=PointIdsList(points=[str(uuid.UUID(source_id))]),wait=True)
