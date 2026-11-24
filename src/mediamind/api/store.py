"""Library store backed by SQLite (see mediamind/db.py). Replaces the old in-memory stub.

Function names are the contract the API and tests use; keep them stable:
    get_item, list_items, search, save_item, soft_delete

Role 2: `search` is still a keyword scorer. Replace its body with hybrid BM25 + vectors + reranker,
always filtered by user_id. Everything else here can stay.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from mediamind.db import connect, init_db, now

init_db()  # create tables and seed demo data on first import

_COLS = "id, user_id, media, kind, thumb, category, title, tags, text, fields, confidence, created_at"


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["tags"] = json.loads(d["tags"])
    d["fields"] = json.loads(d["fields"])
    return d


def get_item(record_id: str) -> dict | None:
    """One record by id, or None. Soft-deleted records count as absent."""
    with connect() as c:
        r = c.execute(f"SELECT {_COLS} FROM items WHERE id = ? AND deleted_at IS NULL", (record_id,)).fetchone()
    return _row(r) if r else None


def list_items(user_id: str, category: str | None = None) -> list[dict]:
    sql = f"SELECT {_COLS} FROM items WHERE user_id = ? AND deleted_at IS NULL"
    args: list[Any] = [user_id]
    if category not in (None, "all"):
        sql += " AND category = ?"
        args.append(category)
    with connect() as c:
        rows = c.execute(sql + " ORDER BY rowid", args).fetchall()
    return [_row(r) for r in rows]


def search(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """Keyword stub. Role 2 replaces this with hybrid BM25 + vectors + reranker, filtered by user_id."""
    words = [w for w in query.lower().replace("?", "").split() if len(w) > 2]
    scored = []
    for r in list_items(user_id):
        hay = " ".join([r["title"], r["category"], " ".join(r["tags"]), r["text"]]).lower()
        s = sum(w in hay for w in words)
        if s:
            scored.append((s, r))
    return [r for _, r in sorted(scored, key=lambda x: -x[0])[:limit]]


def save_item(payload: dict) -> dict:
    """Insert one approved record. Only call this through ApprovalGate.execute()."""
    rid = f"rec{uuid.uuid4().hex[:8]}"
    ts = now()
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)", (payload["user_id"], ts))
        c.execute(
            "INSERT INTO items (id, user_id, media, kind, thumb, category, title, tags, text, fields, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, payload["user_id"], payload["media"], payload.get("kind", "image"), payload.get("thumb"), payload["category"],
             payload["title"], json.dumps(payload.get("tags", [])), payload.get("text", ""),
             json.dumps(payload.get("fields", {})), payload.get("confidence"), ts),
        )
    return get_item(rid)  # type: ignore[return-value]


def soft_delete(user_id: str, record_id: str) -> bool:
    """Hide a record (recoverable). Only the owner can delete. Returns True if something was deleted.
    Like save_item, only call this through the approval gate."""
    with connect() as c:
        cur = c.execute("UPDATE items SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                        (now(), record_id, user_id))
    return cur.rowcount == 1


def user_has_no_password(user_id: str) -> bool:
    with connect() as c:
        r = c.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return r is not None and not r["password_hash"]


def owns_file(user_id: str, name: str) -> bool:
    """True if one of the user's live items uses this media file or thumbnail."""
    with connect() as c:
        return c.execute("SELECT 1 FROM items WHERE user_id = ? AND deleted_at IS NULL AND (media = ? OR thumb = ?)",
                         (user_id, name, name)).fetchone() is not None


# ---------------------------------------------------------------- collections
def normalize_name(name: str) -> str:
    """Collection names: single spaces, at most 60 characters."""
    return " ".join((name or "").split())[:60]


def find_collection(user_id: str, name: str) -> dict | None:
    """The user's collection with this name, ignoring case, or None."""
    with connect() as c:
        r = c.execute("SELECT id, name FROM collections WHERE user_id = ? AND lower(name) = lower(?)",
                      (user_id, normalize_name(name))).fetchone()
    return dict(r) if r else None


def list_collections(user_id: str) -> list[dict]:
    """The user's collections with how many live (not deleted) items each holds."""
    with connect() as c:
        rows = c.execute(
            "SELECT c.id, c.name, COUNT(i.id) AS count FROM collections c "
            "LEFT JOIN item_collections ic ON ic.collection_id = c.id "
            "LEFT JOIN items i ON i.id = ic.item_id AND i.user_id = c.user_id AND i.deleted_at IS NULL "
            "WHERE c.user_id = ? GROUP BY c.id ORDER BY c.rowid", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def collection_items(user_id: str, collection_id: str) -> list[dict]:
    """Items in one of the user's collections. Another user's collection looks empty."""
    with connect() as c:
        rows = c.execute(
            f"SELECT {', '.join('i.' + k.strip() for k in _COLS.split(','))} FROM items i "
            "JOIN item_collections ic ON ic.item_id = i.id JOIN collections c ON c.id = ic.collection_id "
            "WHERE c.id = ? AND c.user_id = ? AND i.user_id = ? AND i.deleted_at IS NULL ORDER BY i.rowid",
            (collection_id, user_id, user_id)).fetchall()
    return [_row(r) for r in rows]


def add_to_collection(payload: dict) -> dict:
    """Create the collection (or reuse one with the same name) and add the items. Only call this through
    ApprovalGate.execute(). Ownership is checked again here, at write time: an item deleted or not owned
    by now is skipped, never added."""
    user_id, name = payload["user_id"], normalize_name(payload["name"])
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)", (user_id, now()))
        r = c.execute("SELECT id FROM collections WHERE user_id = ? AND lower(name) = lower(?)", (user_id, name)).fetchone()
        created = r is None
        cid = f"col{uuid.uuid4().hex[:8]}" if created else r["id"]
        if created:
            c.execute("INSERT INTO collections (id, user_id, name) VALUES (?, ?, ?)", (cid, user_id, name))
        added = 0
        for iid in payload["item_ids"]:
            owned = c.execute("SELECT 1 FROM items WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                              (iid, user_id)).fetchone()
            if owned:
                added += c.execute("INSERT OR IGNORE INTO item_collections (item_id, collection_id) VALUES (?, ?)",
                                   (iid, cid)).rowcount
    return {"id": cid, "name": name, "created": created, "added": added}
