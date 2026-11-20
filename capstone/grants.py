"""One-use write capabilities. Deliberately absent from persistent graph state."""
import threading
import time
from .storage import digest
_lock=threading.Lock()
_grants={}

def issue(run_id,payload):
    with _lock:_grants[run_id]=(digest(payload),time.monotonic()+60)

def consume(run_id,payload,approval_hash):
    with _lock:
        grant=_grants.pop(run_id,None)
    return bool(grant and grant[1]>time.monotonic() and grant[0]==approval_hash==digest(payload))
