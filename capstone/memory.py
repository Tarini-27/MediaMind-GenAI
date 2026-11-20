"""LangGraph Store with SQLite-backed puts; single-process local deployment."""
import asyncio
import json
import threading
from langgraph.store.memory import InMemoryStore
from langgraph.store.base import PutOp
import app

class PersistentStore(InMemoryStore):
    def __init__(self):
        super().__init__()
        self._persist_lock=threading.RLock()
        with app.conn() as c:
            c.execute('CREATE TABLE IF NOT EXISTS graph_memory (namespace TEXT,key TEXT,value TEXT,PRIMARY KEY(namespace,key))')
            rows=c.execute('SELECT * FROM graph_memory').fetchall()
        for r in rows:super().batch([PutOp(tuple(json.loads(r['namespace'])),r['key'],json.loads(r['value']))])

    def batch(self,ops):
        ops=list(ops)
        with self._persist_lock:
            result=super().batch(ops)
            with app.conn() as c:
                for op in ops:
                    if isinstance(op,PutOp):
                        ns=json.dumps(op.namespace)
                        if op.value is None:c.execute('DELETE FROM graph_memory WHERE namespace=? AND key=?',(ns,op.key))
                        else:c.execute('INSERT OR REPLACE INTO graph_memory VALUES(?,?,?)',(ns,op.key,json.dumps(dict(op.value))))
            return result

    async def abatch(self,ops):return await asyncio.to_thread(self.batch,list(ops))
