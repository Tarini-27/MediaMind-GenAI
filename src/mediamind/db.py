"""SQLite library database: schema, connection helper, seed data.

One connection per call (open, work, commit, close). Simple and thread-safe for FastAPI's threadpool.
Path comes from MEDIAMIND_DB (default data/mediamind.sqlite). Tests point it at a temp file.

Every row that holds user data carries user_id. Role 2's queries must always filter by it.
The vector index (Chroma) lives next to this DB and is filtered by user_id the same way.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]


def db_path() -> Path:
    return Path(os.environ.get("MEDIAMIND_DB", ROOT / "data" / "mediamind.sqlite"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    password_hash TEXT                 -- scrypt; NULL = cannot log in (e.g. seed users)
);

-- Logins. Only a SHA-256 of the token is stored, so a copy of the database can't be used to log in.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

-- Past searches, shown back to the same user as suggestions. PII is masked before storing.
CREATE TABLE IF NOT EXISTS searches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(id),
    query       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS searches_user ON searches(user_id, id);

-- Saved, approved records. deleted_at set = soft-deleted (hidden everywhere, recoverable).
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    media       TEXT NOT NULL,                  -- file name under data/media/
    kind        TEXT NOT NULL DEFAULT 'image',  -- image | video
    thumb       TEXT,                           -- thumbnail file name for videos, NULL for images
    category    TEXT NOT NULL,                  -- recipe | workout | place | learning | other | custom
    title       TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',     -- JSON list
    text        TEXT NOT NULL DEFAULT '',       -- OCR / transcript / caption text (source for citations)
    fields      TEXT NOT NULL DEFAULT '{}',     -- JSON: schema-guided extraction (ingredients, steps, ...)
    confidence  REAL,                           -- classifier confidence, NULL if unknown
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_user_cat ON items(user_id, category) WHERE deleted_at IS NULL;

-- Reserved for library.move / user collections (Organizer agent). Unused by the UI today.
CREATE TABLE IF NOT EXISTS collections (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS item_collections (
    item_id        TEXT NOT NULL REFERENCES items(id),
    collection_id  TEXT NOT NULL REFERENCES collections(id),
    PRIMARY KEY (item_id, collection_id)
);

-- Approval queue. Persisted so a restart never loses a pending approval or replays an executed one.
CREATE TABLE IF NOT EXISTS proposals (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    action         TEXT NOT NULL,               -- e.g. library.save
    payload        TEXT NOT NULL,               -- JSON, exactly what the human sees and approves
    status         TEXT NOT NULL,               -- pending | approved | rejected | executed
    approved_hash  TEXT,                        -- hash of the payload at approval time
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_user_status ON proposals(user_id, status);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Synthetic seed: matches scripts/make_sample_media.py. rec99 belongs to another user so isolation is testable.
SEED_ITEMS = [
    # id, user, media, title, category, tags, text
    ("rec1", "demo", "recipe_wrap.png", "No-oven paneer wrap", "recipe", ["no-oven", "high-protein", "vegetarian"], "paneer yoghurt roti wrap no oven"),
    ("rec2", "demo", "recipe_overnight_oats.png", "Overnight oats, 3 ways", "recipe", ["no-oven", "breakfast", "vegetarian"], "oats milk chia overnight fridge"),
    ("rec3", "demo", "recipe_chickpea_salad.png", "High-protein chickpea salad", "recipe", ["no-oven", "high-protein", "vegan"], "chickpeas cucumber lemon salad"),
    ("rec4", "demo", "workout_shoulder.png", "Dumbbell shoulder burn", "workout", ["beginner", "dumbbells"], "lateral raise arnold press front raise"),
    ("rec5", "demo", "workout_beginner_legs.png", "Beginner leg day", "workout", ["beginner", "bodyweight"], "squats lunges glute bridge"),
    ("rec6", "demo", "place_jaipur.png", "Jaipur weekend: Amber Fort + old city", "place", ["short-trip", "heritage"], "amber fort hawa mahal jaipur weekend"),
    ("rec7", "demo", "place_goa.png", "Goa off-season cafes", "place", ["short-trip", "beach"], "goa cafes beach off-season"),
    ("rec8", "demo", "learn_bayes.png", "Bayes theorem cheat sheet", "learning", ["statistics"], "bayes theorem prior posterior"),
    ("rec9", "demo", "learn_sql_joins.png", "SQL joins diagram", "learning", ["sql"], "inner left right outer join"),
    ("rec99", "other", "recipe_wrap.png", "Someone else's secret", "recipe", [], "private"),
]
# Videos: id, user, media, thumb, title, category, tags, text (transcript stand-in)
SEED_VIDEOS = [
    ("rec10", "demo", "workout_full_body.mp4", "workout_full_body_thumb.jpg", "10-minute full body routine", "workout",
     ["beginner", "bodyweight", "video"], "squats lunges glute bridge plank full body ten minutes"),
]


def _seed(conn: sqlite3.Connection) -> None:
    ts = now()
    for user in {row[1] for row in SEED_ITEMS}:
        conn.execute("INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)", (user, ts))
    for rid, user, media, title, cat, tags, text in SEED_ITEMS:
        conn.execute(
            "INSERT INTO items (id, user_id, media, kind, category, title, tags, text, created_at) "
            "VALUES (?, ?, ?, 'image', ?, ?, ?, ?, ?)",
            (rid, user, media, cat, title, json.dumps(tags), text, ts),
        )
    for rid, user, media, thumb, title, cat, tags, text in SEED_VIDEOS:
        conn.execute(
            "INSERT INTO items (id, user_id, media, kind, thumb, category, title, tags, text, created_at) "
            "VALUES (?, ?, ?, 'video', ?, ?, ?, ?, ?, ?)",
            (rid, user, media, thumb, cat, title, json.dumps(tags), text, ts),
        )


def init_db(seed: bool = True) -> None:
    """Create tables if missing. Seed demo data once, only into an empty items table.
    Set MEDIAMIND_SEED=0 to skip seeding (e.g. when loading your own corpus)."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        # tiny migration: databases created before video support have no `thumb` column
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        if "thumb" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN thumb TEXT")
        if "password_hash" not in {r["name"] for r in conn.execute("PRAGMA table_info(users)")}:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        empty = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
        if seed and empty and os.environ.get("MEDIAMIND_SEED", "1") != "0":
            _seed(conn)
