"""Login, sign-up, sessions and search history (Role 4).

Who the caller is comes from the session cookie, never from a `user_id` the browser sends: before this, any
client could ask for `user_id=demo` and get demo's library. `who()` is called by every endpoint.

- Passwords: scrypt (memory-hard, standard library), random salt per user, constant-time comparison.
- Sessions: a random 256-bit token in an HttpOnly, SameSite=Lax cookie. Only its SHA-256 is stored.
- Brute force: after N failed logins the username is locked for a few minutes (in memory; per process).
- Unknown user and wrong password give the same message, and both run scrypt, so usernames can't be probed.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from mediamind.config import get_config
from mediamind.control.guardrails import mask_pii
from mediamind.db import connect, now

COOKIE = "mm_session"
USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
_N, _R, _P = 2 ** 14, 8, 1
_failed: dict[str, list[float]] = {}        # username -> times of recent failures


def auth_required() -> bool:
    """`auth.required` in the config decides; MEDIAMIND_AUTH=on/off overrides it (tests use both)."""
    env = os.environ.get("MEDIAMIND_AUTH", "").lower()
    return env == "on" if env in ("on", "off") else get_config().auth.required


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored:
        hashlib.scrypt(password.encode(), salt=b"0" * 16, n=_N, r=_R, p=_P, dklen=32)   # same cost either way
        return False
    _, salt, want = stored.split("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P, dklen=32)
    return hmac.compare_digest(got.hex(), want)


def validate(username: str, password: str) -> str:
    u = (username or "").strip().lower()
    if not USERNAME.match(u):
        raise HTTPException(400, "username: 3 to 32 characters, letters, digits, . _ -")
    if not 8 <= len(password or "") <= 128:
        raise HTTPException(400, "password: 8 to 128 characters")
    return u


def create_user(username: str, password: str) -> str:
    u = validate(username, password)
    with connect() as c:
        if c.execute("SELECT 1 FROM users WHERE id = ?", (u,)).fetchone():
            raise HTTPException(409, "that username is taken")
        c.execute("INSERT INTO users (id, created_at, password_hash) VALUES (?, ?, ?)", (u, now(), hash_password(password)))
    return u


def set_password(user_id: str, password: str) -> None:
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)", (user_id, now()))
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))


def authenticate(username: str, password: str) -> str:
    cfg = get_config().auth
    u = (username or "").strip().lower()
    recent = [t for t in _failed.get(u, []) if t > time.time() - cfg.lockout_minutes * 60]
    _failed[u] = recent
    if len(recent) >= cfg.max_failed_logins:
        raise HTTPException(429, f"too many attempts; try again in {cfg.lockout_minutes} minutes")
    with connect() as c:
        r = c.execute("SELECT password_hash FROM users WHERE id = ?", (u,)).fetchone()
    if not check_password(password or "", r["password_hash"] if r else None):
        _failed[u].append(time.time())
        raise HTTPException(401, "wrong username or password")
    _failed.pop(u, None)
    return u


# ------------------------------------------------------------------- sessions
def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(response: Response, user_id: str) -> None:
    cfg = get_config().auth
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=cfg.session_hours)
    with connect() as c:
        c.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                  (_digest(token), user_id, now(), expires.isoformat(timespec="seconds")))
    response.set_cookie(COOKIE, token, max_age=cfg.session_hours * 3600, httponly=True, samesite="lax",
                        secure=cfg.cookie_secure, path="/")


def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with connect() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))
    response.delete_cookie(COOKIE, path="/")


def session_user(request: Request) -> str | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with connect() as c:
        r = c.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (_digest(token),)).fetchone()
        if r and r["expires_at"] < now():
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))
            return None
    return r["user_id"] if r else None


def who(request: Request, claimed: str | None = None) -> str:
    """The caller's user id. With login on, only the session decides and any claimed id is ignored."""
    if not auth_required():
        # Login off (team development): trust the request, or fall back to the single demo user.
        return claimed or get_config().auth.default_user
    user = session_user(request)
    if not user:
        raise HTTPException(401, "log in first")
    return user


# -------------------------------------------------------------- search history
def record_search(user_id: str, query: str) -> None:
    q = " ".join(mask_pii(query).split())[:200]
    if not q:
        return
    keep = get_config().auth.history_size
    with connect() as c:
        c.execute("DELETE FROM searches WHERE user_id = ? AND lower(query) = lower(?)", (user_id, q))   # move to top
        c.execute("INSERT INTO searches (user_id, query, created_at) VALUES (?, ?, ?)", (user_id, q, now()))
        c.execute("DELETE FROM searches WHERE user_id = ? AND id NOT IN "
                  "(SELECT id FROM searches WHERE user_id = ? ORDER BY id DESC LIMIT ?)", (user_id, user_id, keep))


def history(user_id: str, prefix: str = "", limit: int = 8) -> list[str]:
    with connect() as c:
        rows = c.execute("SELECT query FROM searches WHERE user_id = ? AND lower(query) LIKE ? ESCAPE '\\' "
                         "ORDER BY id DESC LIMIT ?",
                         (user_id, "%" + re.sub(r"([%_\\])", r"\\\1", prefix.lower().strip()) + "%", limit)).fetchall()
    return [r["query"] for r in rows]


def clear_history(user_id: str) -> int:
    with connect() as c:
        return c.execute("DELETE FROM searches WHERE user_id = ?", (user_id,)).rowcount
