"""Durable preferences, notebook actions and human-reviewed development lessons."""
import hashlib
import hmac
import json
import time
import uuid
import app
from .security import scrub


def init():
    with app.conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY,value TEXT,expires REAL);
        CREATE TABLE IF NOT EXISTS notebooks (id TEXT PRIMARY KEY,run_id TEXT UNIQUE,payload TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS lessons (id TEXT PRIMARY KEY,condition TEXT,lesson TEXT,status TEXT,reason TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS playbook_versions (version TEXT PRIMARY KEY,lessons TEXT,created REAL);
        ''')


def memory():
    with app.conn() as c:
        c.execute('DELETE FROM preferences WHERE expires<?',(time.time(),))
        return {x['key']:json.loads(x['value']) for x in c.execute('SELECT * FROM preferences')}


def set_memory(key,value,consent=False):
    if key not in {'answer_style','preferred_category'}:raise ValueError('Unsupported preference.')
    if not consent:raise ValueError('Explicit consent is required to store a preference.')
    if key=='answer_style' and value not in {'brief','detailed'}:raise ValueError('Choose brief or detailed.')
    if key=='preferred_category' and value not in app.TOPICS+['all']:raise ValueError('Unsupported category.')
    with app.conn() as c:
        c.execute('INSERT OR REPLACE INTO preferences VALUES(?,?,?)',(key,json.dumps(value),time.time()+30*86400))
    return memory()


def delete_memory():
    with app.conn() as c:c.execute('DELETE FROM preferences')


def digest(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def publish(run_id,payload,approval_hash):
    if not hmac.compare_digest(digest(payload),approval_hash):raise ValueError('Approval does not match the exact note.')
    if set(payload)-{'title','claims','unknowns'}:raise ValueError('Unexpected note fields.')
    # Recheck sources at commit, including content versions, so approval cannot
    # publish a claim whose original was removed or changed during the pause.
    from .retrieval import get_passage
    for claim in payload.get('claims',[]):
        for citation in claim.get('citations',[]):
            p=get_passage(citation['id'])
            if not p or p['source_version']!=citation['source_version']:raise ValueError('Source changed. Generate and review a new note.')
    ident=uuid.uuid4().hex
    with app.conn() as c:
        old=c.execute('SELECT id FROM notebooks WHERE run_id=?',(run_id,)).fetchone()
        if old:return {'id':old['id'],'published':True,'duplicate':True}
        c.execute('INSERT INTO notebooks VALUES(?,?,?,?)',(ident,run_id,json.dumps(scrub(payload)),time.time()))
    return {'id':ident,'published':True}


def notebook():
    with app.conn() as c:return [{'id':r['id'],'note':json.loads(r['payload']),'created':r['created']} for r in c.execute('SELECT * FROM notebooks ORDER BY created DESC')]


def propose_lesson(condition,lesson):
    ident=uuid.uuid4().hex
    with app.conn() as c:c.execute('INSERT INTO lessons VALUES(?,?,?,?,?,?)',(ident,str(condition)[:200],str(lesson)[:1000],'pending','',time.time()))
    return ident


def review_lesson(ident,approved,reason):
    if not reason.strip():raise ValueError('Record a review reason.')
    with app.conn() as c:
        if not c.execute('SELECT 1 FROM lessons WHERE id=?',(ident,)).fetchone():raise ValueError('Lesson not found.')
        c.execute('UPDATE lessons SET status=?,reason=? WHERE id=?',('approved' if approved else 'rejected',reason[:500],ident))


def lessons(query,version=''):
    with app.conn() as c:
        if version:
            row=c.execute('SELECT lessons FROM playbook_versions WHERE version=?',(version,)).fetchone()
            if not row:raise ValueError('Unknown frozen playbook version.')
            candidates=json.loads(row['lessons'])
        else:candidates=[dict(r) for r in c.execute("SELECT * FROM lessons WHERE status='approved'")]
    qt=set(app.tokens(query))
    return [r for r in candidates if qt & set(app.tokens(r['condition']))][:3]


def freeze():
    with app.conn() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM lessons WHERE status='approved' ORDER BY id")]
        version=digest(rows)[:16]
        c.execute('INSERT OR IGNORE INTO playbook_versions VALUES(?,?,?)',(version,json.dumps(rows),time.time()))
    return version
