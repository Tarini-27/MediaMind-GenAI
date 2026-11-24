"""SQLite-backed proposal storage for ApprovalGate (table `proposals`, see mediamind/db.py)."""
from __future__ import annotations

import json

from mediamind.control.approval import Proposal, Status
from mediamind.db import connect, now


def _to_proposal(r) -> Proposal:
    return Proposal(user_id=r["user_id"], action=r["action"], payload=json.loads(r["payload"]),
                    id=r["id"], status=Status(r["status"]), approved_hash=r["approved_hash"])


class SqliteProposalRepo:
    def save(self, p: Proposal) -> None:
        ts = now()
        with connect() as c:
            c.execute(
                "INSERT INTO proposals (id, user_id, action, payload, status, approved_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, status = excluded.status, "
                "approved_hash = excluded.approved_hash, updated_at = excluded.updated_at",
                (p.id, p.user_id, p.action, json.dumps(p.payload, sort_keys=True), p.status.value,
                 p.approved_hash, ts, ts),
            )

    def get(self, proposal_id: str) -> Proposal | None:
        with connect() as c:
            r = c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        return _to_proposal(r) if r else None

    def pending(self, user_id: str) -> list[Proposal]:
        with connect() as c:
            rows = c.execute("SELECT * FROM proposals WHERE user_id = ? AND status = 'pending' ORDER BY rowid",
                             (user_id,)).fetchall()
        return [_to_proposal(r) for r in rows]

    def claim(self, p: Proposal) -> bool:
        """One UPDATE decides the winner: only an APPROVED row with the approved hash can become EXECUTED."""
        with connect() as c:
            cur = c.execute("UPDATE proposals SET status = 'executed', updated_at = ? "
                            "WHERE id = ? AND status = 'approved' AND approved_hash = ?",
                            (now(), p.id, p.approved_hash))
        return cur.rowcount == 1
