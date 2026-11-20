"""Shared relevance checks for saved-note search and evidence retrieval.

RRF and cosine similarity rank candidates; they do not establish relevance. The
cross-encoder cutoff is model-specific and must be evaluated on labelled cases.
"""
import os
import re
import threading

# Conversational framing must not turn an unrelated source into a search hit.
QUERY_FRAMING=set('about related regarding concerning where when who whose whom there here was were be been being remember remembered rememberings saw seen watched watching one something anything stuff thing things creator creators person people someone somebody us you your we our give get got help want wanted looking look search searching contains containing content tell tells told say says said mention mentions mentioned explain explains explained video videos reel reels post posts save saves saved please exact many amount amounts quantity quantities use uses using used ingredients ingredient need needs require requires'.split())
BROAD_ACTIONS={'cook','cooking','make','making','prepare','preparing','preparation'}
_encoder=None
_encoder_name=None
_encoder_lock=threading.Lock()


def query_terms(query,tokenize):
    terms=list(dict.fromkeys(t for t in tokenize(query) if t not in QUERY_FRAMING))
    if terms and any(t not in BROAD_ACTIONS for t in terms):return terms
    if re.search(r'\b(recipe|recipes|cooking|cook|food)\b',query,re.I):return ['food']
    return terms


def keyword_match(query,terms,document_terms):
    if not terms:return False
    available=set(document_terms)
    if re.search(r'\b(?:or)\b',query,re.I):return any(t in available for t in terms)
    # Keep each explicitly named topic: "cook paneer" cannot degrade to "cook".
    return all(t in available for t in terms)


def rerank_candidates(query,candidates,model_name=None):
    """Return retained keys with scores and a warning, never silently top-k everything.

    candidates is a list of (stable key, evidence/text). None means the reranker
    is unavailable: callers must then use their independently checked lexical set.
    """
    model_name=os.environ.get('RERANK_MODEL','') if model_name is None else model_name
    if not model_name:return None,'Relevance reranker is not configured; using keyword matches only.'
    global _encoder,_encoder_name
    try:
        with _encoder_lock:
            if _encoder is None or _encoder_name!=model_name:
                from sentence_transformers import CrossEncoder
                _encoder=CrossEncoder(model_name,trust_remote_code=False)
                _encoder_name=model_name
            if not candidates:return [],''
            scores=_encoder.predict([(query,text) for _,text in candidates])
        cutoff=float(os.environ.get('RERANK_MIN_SCORE','0'))
        # The shipped ms-marco TinyBERT model produces logits. Zero is a
        # conservative starting gate, not a calibrated probability or accuracy claim.
        ranked=sorted(((key,float(score)) for (key,_),score in zip(candidates,scores)
                       if float(score)>cutoff),key=lambda pair:pair[1],reverse=True)
        return ranked,''
    except (ImportError,OSError,ValueError,RuntimeError):
        return None,'Relevance reranker unavailable; using keyword matches only.'
