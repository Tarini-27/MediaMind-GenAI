"""MediaMind API. Every question is a traced run (POST /runs, or /ask for the UI); which code answers it is
chosen by experiment.agent_mode (see mediamind/runners.py). Role 3 registers the graph there.

Control wiring: upload checks, injection scan, PII masking, approval gate on every write, output
citation check, run traces in data/traces/, Prometheus metrics.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from mediamind import media
from mediamind.metrics import BLOCKS, LAT, REQS
from mediamind.runners import execute_run
from mediamind.runs import load_trace, run_scope
from mediamind.api import auth, store
from mediamind.api.auth import who
from mediamind.config import get_config
from mediamind.control.approval import ApprovalError, ApprovalGate
from mediamind.control.guardrails import check_image_bytes, check_upload, check_video, detect_injection
from mediamind.control.repos import SqliteProposalRepo

app = FastAPI(title="MediaMind API", version=get_config().version)
gate = ApprovalGate(SqliteProposalRepo())   # approvals persist in SQLite, so a restart loses nothing

# MEDIAMIND_DATA lets tests use a temp folder. data/media = approved files (served),
# data/uploads/pending/<proposal_id>/ = not yet approved (never served publicly, removed on reject).
DATA_DIR = Path(os.environ.get("MEDIAMIND_DATA", Path(__file__).resolve().parents[3] / "data"))
MEDIA_DIR = DATA_DIR / "media"
PENDING_DIR = DATA_DIR / "uploads" / "pending"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
PENDING_DIR.mkdir(parents=True, exist_ok=True)

EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm"}
# The only fields a human edit may change, per kind of proposal. Everything else is server-owned.
EDITABLE = {"library.save": {"title", "category", "tags"}, "library.collect": {"name"}}
MAX_COLLECT = 200
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# Local demo login for the seeded library. Set MEDIAMIND_DEMO_PASSWORD in .env to change it; never deploy the default.
if os.environ.get("MEDIAMIND_SEED", "1") != "0" and store.user_has_no_password("demo"):
    auth.set_password("demo", os.environ.get("MEDIAMIND_DEMO_PASSWORD", "mediamind-demo"))


@app.middleware("http")
async def media_owner_only(request: Request, call_next):
    """Approved files are only served to their owner. Without this, anyone who knows a file name could fetch it."""
    if request.url.path.startswith("/media/") and auth.auth_required():
        user = auth.session_user(request)
        if not user or not store.owns_file(user, request.url.path.removeprefix("/media/")):
            return Response(status_code=404)
    return await call_next(request)


class AskIn(BaseModel):
    user_id: str | None = None        # ignored when logged in: the session decides
    question: str


class RunIn(BaseModel):
    user_id: str | None = None        # ignored when logged in: the session decides
    mode: str = "ask"                 # ask today; save and others once the agent graph exists
    question: str | None = None
    case_id: str | None = None        # set by the evaluation harness so traces map to cases
    input: dict[str, Any] = {}        # any other fields the runner needs


class ProposeIn(BaseModel):
    user_id: str | None = None        # ignored when logged in: the session decides
    filename: str
    content_type: str
    size_bytes: int
    extracted_text: str = ""        # OCR/transcript text, scanned for injection
    title: str
    category: str


class CollectIn(BaseModel):
    user_id: str | None = None        # ignored when logged in: the session decides
    name: str                         # usually the search question
    item_ids: list[str]


class DeleteIn(BaseModel):
    user_id: str | None = None        # ignored when logged in: the session decides


class Credentials(BaseModel):
    username: str
    password: str


class DecisionIn(BaseModel):
    user_id: str | None = None        # ignored when logged in: the session decides
    payload: dict[str, Any] | None = None   # only for edit


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/auth/signup")
def signup(body: Credentials, response: Response):
    user = auth.create_user(body.username, body.password)
    auth.start_session(response, user)
    return {"user_id": user}


@app.post("/auth/login")
def login(body: Credentials, response: Response):
    user = auth.authenticate(body.username, body.password)
    auth.start_session(response, user)
    return {"user_id": user}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    auth.end_session(request, response)
    return {"ok": True}


@app.get("/auth/me")
def me(request: Request):
    if not auth.auth_required():
        return {"user_id": get_config().auth.default_user, "login": False}   # the UI skips the login screen
    user = auth.session_user(request)
    if not user:
        raise HTTPException(401, "not logged in")
    return {"user_id": user, "login": True}


@app.get("/history")
def search_history(request: Request, q: str = "", user_id: str | None = None):
    """The caller's recent searches, newest first, filtered by what they have typed so far."""
    return auth.history(who(request, user_id), q)


@app.delete("/history")
def delete_history(request: Request, user_id: str | None = None):
    return {"deleted": auth.clear_history(who(request, user_id))}


@app.get("/items")
def items(request: Request, user_id: str | None = None, category: str = "all", collection: str | None = None):
    user_id = who(request, user_id)
    if collection:
        return store.collection_items(user_id, collection)
    return store.list_items(user_id, category)


@app.get("/collections")
def collections(request: Request, user_id: str | None = None):
    user_id = who(request, user_id)
    return store.list_collections(user_id)


@app.post("/collections/propose")
def propose_collection(body: CollectIn, request: Request):
    """Group items (e.g. search results) into a named collection. Like any write, this is only a proposal
    until a person approves it. Items must be the caller's own; the name is checked like any user text."""
    uid = who(request, body.user_id)
    name = store.normalize_name(body.name)
    if not name:
        raise HTTPException(400, "collection name is empty")
    ids = list(dict.fromkeys(body.item_ids))          # dedupe, keep order
    if not ids or len(ids) > MAX_COLLECT:
        raise HTTPException(400, f"give between 1 and {MAX_COLLECT} items")
    if get_config().experiment.defences and (scan := detect_injection(name)).flagged:
        BLOCKS.labels("input_injection").inc()
        raise HTTPException(400, f"collection name looks like an instruction: {scan.reason}")
    owned = [store.get_item(i) for i in ids]
    if any(r is None or r["user_id"] != uid for r in owned):
        raise HTTPException(400, "unknown items")       # other users' items look the same as missing ones
    existing = store.find_collection(uid, name)
    payload = {"user_id": uid, "name": name, "item_ids": ids,
               "item_titles": [r["title"] for r in owned], "existing": bool(existing)}
    p = gate.propose(uid, "library.collect", payload)
    return {"proposal_id": p.id, "hash": p.payload_hash, "payload": p.payload, "status": p.status}


@app.post("/items/{item_id}/delete")
def propose_delete(item_id: str, body: DeleteIn, request: Request):
    """Propose hiding one of the caller's items. Nothing changes until a person approves; the delete is soft
    (the row is kept with deleted_at set), so a mistake can be undone in the database."""
    uid = who(request, body.user_id)
    rec = store.get_item(item_id)
    if rec is None or rec["user_id"] != uid:
        raise HTTPException(404, "unknown item")         # other users' items look the same as missing ones
    payload = {"user_id": uid, "item_id": item_id, "title": rec["title"], "category": rec["category"],
               "kind": rec["kind"], "media": rec["media"], "thumb": rec.get("thumb")}
    p = gate.propose(uid, "library.soft_delete", payload)
    return {"proposal_id": p.id, "hash": p.payload_hash, "payload": p.payload, "status": p.status}


def _delete(payload: dict[str, Any]) -> dict:
    """Writer for library.soft_delete. Ownership is checked again inside soft_delete, at write time."""
    if not store.soft_delete(payload["user_id"], payload["item_id"]):
        raise ApprovalError("item is already gone; nothing deleted")
    return {"id": payload["item_id"], "deleted": True}


@app.post("/runs")
def create_run(body: RunIn, request: Request):
    """Run one request end to end and write its trace. Used by the evaluation harness."""
    uid = who(request, body.user_id)
    req = {**body.input, **({"question": body.question} if body.question is not None else {})}
    run = execute_run(user_id=uid, mode=body.mode, request=req, case_id=body.case_id)
    REQS.labels("runs", run.status).inc()
    return {"run_id": run.run_id, "case_id": run.case_id, "status": run.status, "runner": run.runner,
            "output": run.output, "error": run.error, "latency_ms": run.elapsed_ms(),
            "totals": run.to_trace()["totals"], "trace": f"/runs/{run.run_id}"}


@app.get("/runs/{run_id}")
def get_run(run_id: str, request: Request, user_id: str | None = None):
    """A run's trace, for its owner only (other users' runs look absent)."""
    user_id = who(request, user_id)
    trace = load_trace(run_id)
    if trace is None or trace["user_id"] != user_id:
        raise HTTPException(404, "run not found")
    return trace


@app.post("/ask")
def ask(body: AskIn, request: Request):
    """The UI's search box. Same traced run as /runs, returned in the shape the UI expects."""
    uid = who(request, body.user_id)
    t0 = time.time()
    run = execute_run(user_id=uid, mode="ask", request={"question": body.question})
    REQS.labels("ask", run.status).inc()
    LAT.labels("ask").observe(time.time() - t0)
    if run.status not in ("ok", "blocked") or not isinstance(run.output, dict):
        raise HTTPException(504 if run.status == "timeout" else 500,
                            {"message": "the run failed", "run_id": run.run_id, "status": run.status})
    if not run.output.get("blocked"):
        auth.record_search(uid, body.question)   # blocked questions (e.g. injections) are never suggested back
    return {**run.output, "run_id": run.run_id}


@app.post("/uploads/propose")
def propose_upload(body: ProposeIn, request: Request):
    """Upload step 1: metadata checks, then a PENDING save proposal. Nothing is saved until a human approves.

    The stored file name is assigned here by the server (never the caller's name), so uploads can't
    overwrite each other or existing media.
    """
    uid = who(request, body.user_id)
    cfg = get_config()
    is_video = body.content_type.startswith("video/")
    if cfg.experiment.defences:
        max_mb = cfg.guardrails.max_video_mb if is_video else cfg.guardrails.max_upload_mb
        chk = check_upload(body.filename, body.content_type, body.size_bytes, cfg.guardrails.allowed_types, max_mb)
        if not chk.ok:
            BLOCKS.labels("input_file").inc()
            raise HTTPException(400, chk.reason)
        if (scan := detect_injection(body.extracted_text)).flagged:
            BLOCKS.labels("input_injection").inc()
            raise HTTPException(400, f"embedded instruction detected: {scan.reason}")
    if body.content_type not in EXT:
        raise HTTPException(400, f"type {body.content_type!r} not supported")
    stored = f"{uuid.uuid4().hex[:16]}{EXT[body.content_type]}"
    payload = {
        "user_id": uid, "media": stored, "kind": "video" if is_video else "image",
        "thumb": f"{Path(stored).stem}_thumb.jpg" if is_video else None,
        "original_name": Path(body.filename).name[:120], "content_type": body.content_type,
        "title": body.title, "category": body.category,
    }
    p = gate.propose(uid, "library.save", payload)
    return {"proposal_id": p.id, "hash": p.payload_hash, "payload": p.payload, "status": p.status}


def _pending(pid: str) -> Path:
    return PENDING_DIR / pid


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _refuse_upload(pid: str, user_id: str, layer: str, reason: str):
    shutil.rmtree(_pending(pid), ignore_errors=True)
    gate.reject(pid, user_id)
    BLOCKS.labels(layer).inc()
    raise HTTPException(400, reason)


@app.post("/uploads/{pid}/blob")
async def upload_blob(pid: str, request: Request, user_id: str | None = None):
    """Upload step 2: the file bytes. Accepted once, only while pending, into the pending folder.

    The bytes are checked (real image / readable video within the length limit), and their sha256 is
    written into the payload. Approval then covers the exact bytes too, not just the title.
    """
    user_id = who(request, user_id)
    cfg = get_config()
    p = _guard(lambda: gate.get(pid, user_id))
    if p.status.value != "pending" or "sha256" in p.payload:
        raise HTTPException(409, "file already uploaded or proposal no longer pending")
    is_video = p.payload["kind"] == "video"
    max_mb = cfg.guardrails.max_video_mb if is_video else cfg.guardrails.max_upload_mb
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"file larger than {max_mb} MB")

    folder = _pending(pid)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / p.payload["media"]
    path.write_bytes(data)
    extra: dict[str, Any] = {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}

    if is_video:
        usable, why = media.ffmpeg_status()
        if not usable:
            _refuse_upload(pid, user_id, "input_file", f"video can't be processed on this server: {why}")
        info = media.probe(path)
        if cfg.experiment.defences:
            chk = check_video(info, cfg.guardrails.max_video_seconds)
            if not chk.ok:
                _refuse_upload(pid, user_id, "input_file", chk.reason)
        if info:
            extra["duration_s"] = round(info["duration"], 1)
        if not media.make_thumbnail(path, folder / p.payload["thumb"]):
            extra["thumb"] = None
    elif cfg.experiment.defences:
        chk = check_image_bytes(data)
        if not chk.ok:
            _refuse_upload(pid, user_id, "input_file", chk.reason)

    p = _guard(lambda: gate.edit(pid, user_id, {**p.payload, **extra}))   # still pending; hash now covers bytes
    return {"stored": p.payload["media"], "bytes": len(data), "sha256": extra["sha256"], "hash": p.payload_hash,
            "duration_s": p.payload.get("duration_s")}


@app.get("/uploads/{pid}/preview")
def preview(pid: str, request: Request, user_id: str | None = None):
    """Let the owner see what they are about to approve. Videos show their thumbnail."""
    user_id = who(request, user_id)
    p = _guard(lambda: gate.get(pid, user_id))
    if p.status.value != "pending":
        raise HTTPException(404, "no pending file")
    name = p.payload.get("thumb") or p.payload["media"]
    path = _pending(pid) / Path(name).name
    if not path.exists():
        raise HTTPException(404, "no file uploaded yet")
    return FileResponse(path)


@app.get("/approvals")
def approvals(request: Request, user_id: str | None = None):
    user_id = who(request, user_id)
    return [{"id": p.id, "action": p.action, "payload": p.payload, "hash": p.payload_hash}
            for p in gate.pending(user_id)]


def _guard(fn):
    try:
        return fn()
    except ApprovalError as e:
        raise HTTPException(409, str(e))


def _commit(pid: str, payload: dict[str, Any]) -> dict:
    """The writer the gate runs after approval: verify bytes, move files out of pending, save the record."""
    folder = _pending(pid)
    src = folder / payload["media"]
    if "sha256" not in payload or not src.exists():
        raise ApprovalError("file not uploaded")
    if _sha256(src) != payload["sha256"]:
        raise ApprovalError("file changed after approval; nothing saved")
    os.replace(src, MEDIA_DIR / payload["media"])
    if payload.get("thumb") and (folder / payload["thumb"]).exists():
        os.replace(folder / payload["thumb"], MEDIA_DIR / payload["thumb"])
    shutil.rmtree(folder, ignore_errors=True)
    return store.save_item(payload)


@app.post("/approvals/{pid}/approve")
def approve(pid: str, body: DecisionIn, request: Request):
    uid = who(request, body.user_id)
    with run_scope(user_id=uid, mode="approve", input={"proposal_id": pid}) as run:
        current = _guard(lambda: gate.get(pid, uid))
        if current.action == "library.save":
            if "sha256" not in current.payload:
                raise HTTPException(409, "file not uploaded yet")
            writer = lambda payload: _commit(pid, payload)          # noqa: E731
        elif current.action == "library.collect":
            writer = store.add_to_collection
        elif current.action == "library.soft_delete":
            writer = _delete
        else:
            raise HTTPException(409, f"no writer for {current.action!r}")
        p = _guard(lambda: gate.approve(pid, uid))
        run.event("approval", "approved", proposal_id=pid, hash=p.approved_hash, action=p.action)
        rec = _guard(lambda: gate.execute(pid, uid, writer))
        run.event("approval", "executed", proposal_id=pid, action=p.action, record_id=rec["id"])
        run.output = {"action": p.action, "id": rec["id"]}
    REQS.labels("approve", "ok").inc()
    key = {"library.save": "record", "library.collect": "collection"}.get(current.action, "deleted")
    return {"status": "deleted" if key == "deleted" else "saved", key: rec, "approved_hash": p.approved_hash, "run_id": run.run_id}


@app.post("/approvals/{pid}/edit")
def edit(pid: str, body: DecisionIn, request: Request):
    """Edit voids any prior approval. Only the fields in EDITABLE for that action can change."""
    uid = who(request, body.user_id)
    current = _guard(lambda: gate.get(pid, uid))
    changes = {k: v for k, v in (body.payload or {}).items() if k in EDITABLE.get(current.action, set())}
    if "name" in changes:
        changes["name"] = store.normalize_name(str(changes["name"]))
        if not changes["name"]:
            raise HTTPException(400, "collection name is empty")
    p = _guard(lambda: gate.edit(pid, uid, {**current.payload, **changes}))
    return {"status": p.status, "hash": p.payload_hash, "payload": p.payload}


@app.post("/approvals/{pid}/reject")
def reject(pid: str, body: DecisionIn, request: Request):
    uid = who(request, body.user_id)
    _guard(lambda: gate.reject(pid, uid))
    shutil.rmtree(_pending(pid), ignore_errors=True)       # rejected files are deleted, never kept
    return {"status": "rejected"}
