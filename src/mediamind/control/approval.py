"""Approval gate: a human approves the EXACT payload; any change voids the approval.

Framework-agnostic on purpose. Role 3 wraps `ApprovalGate` inside LangGraph's interrupt():
    decision = interrupt({"proposal_id": p.id, "payload": p.payload, "hash": p.payload_hash})
    -> on resume, call gate.approve / gate.edit / gate.reject, then gate.execute(...)

Storage is pluggable: MemoryProposalRepo (default, used in unit tests) or SqliteProposalRepo
(mediamind/control/repos.py, used by the API so approvals survive a restart).
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


class Status(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ApprovalError(Exception):
    """Raised when a write is attempted without a valid approval for that exact payload."""


def payload_hash(user_id: str, action: str, payload: dict[str, Any]) -> str:
    """Canonical hash of (user, action, payload). Key order and whitespace do not matter."""
    canonical = json.dumps(
        {"user_id": user_id, "action": action, "payload": payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Proposal:
    user_id: str
    action: str                      # e.g. "library.save"
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: Status = Status.PENDING
    approved_hash: str | None = None  # hash the human actually approved

    @property
    def payload_hash(self) -> str:
        return payload_hash(self.user_id, self.action, self.payload)


class ProposalRepo(Protocol):
    def save(self, p: Proposal) -> None: ...
    def get(self, proposal_id: str) -> Proposal | None: ...
    def pending(self, user_id: str) -> list[Proposal]: ...
    def claim(self, p: Proposal) -> bool:
        """Atomically move APPROVED -> EXECUTED. True for exactly one caller, even under concurrency."""
        ...


class MemoryProposalRepo:
    def __init__(self) -> None:
        self._d: dict[str, Proposal] = {}
        self._lock = threading.Lock()

    def save(self, p: Proposal) -> None:
        self._d[p.id] = p

    def get(self, proposal_id: str) -> Proposal | None:
        return self._d.get(proposal_id)

    def pending(self, user_id: str) -> list[Proposal]:
        return [p for p in self._d.values() if p.user_id == user_id and p.status == Status.PENDING]

    def claim(self, p: Proposal) -> bool:
        with self._lock:
            if p.status != Status.APPROVED:
                return False
            p.status = Status.EXECUTED
            return True


class ApprovalGate:
    def __init__(self, repo: ProposalRepo | None = None) -> None:
        self._repo: ProposalRepo = repo or MemoryProposalRepo()

    # -- create / read -------------------------------------------------
    def propose(self, user_id: str, action: str, payload: dict[str, Any]) -> Proposal:
        p = Proposal(user_id=user_id, action=action, payload=dict(payload))
        self._repo.save(p)
        return p

    def get(self, proposal_id: str, user_id: str) -> Proposal:
        p = self._repo.get(proposal_id)
        if p is None or p.user_id != user_id:        # ownership: other users' proposals look absent
            raise ApprovalError("proposal not found")
        return p

    def pending(self, user_id: str) -> list[Proposal]:
        return self._repo.pending(user_id)

    # -- human decisions -----------------------------------------------
    def approve(self, proposal_id: str, user_id: str) -> Proposal:
        p = self.get(proposal_id, user_id)
        if p.status != Status.PENDING:
            raise ApprovalError(f"cannot approve a {p.status.value} proposal")
        p.status = Status.APPROVED
        p.approved_hash = p.payload_hash            # bind approval to what the human saw
        self._repo.save(p)
        return p

    def edit(self, proposal_id: str, user_id: str, new_payload: dict[str, Any]) -> Proposal:
        """Editing changes the payload, so any earlier approval is void: back to PENDING."""
        p = self.get(proposal_id, user_id)
        if p.status in (Status.EXECUTED, Status.REJECTED):
            raise ApprovalError(f"cannot edit a {p.status.value} proposal")
        p.payload = dict(new_payload)
        p.status = Status.PENDING
        p.approved_hash = None
        self._repo.save(p)
        return p

    def reject(self, proposal_id: str, user_id: str) -> Proposal:
        p = self.get(proposal_id, user_id)
        if p.status == Status.EXECUTED:
            raise ApprovalError("already executed")
        p.status = Status.REJECTED
        p.approved_hash = None
        self._repo.save(p)
        return p

    # -- the only path to a write --------------------------------------
    def execute(self, proposal_id: str, user_id: str, writer: Callable[[dict[str, Any]], Any]) -> Any:
        """Run `writer(payload)` only if approved AND the payload still matches what was approved.

        The hash is recomputed here from the stored payload, so tampering after approval (including
        direct edits to the database row) is caught. The claim is atomic, so a double click or a
        retry cannot write twice.
        """
        p = self.get(proposal_id, user_id)
        if p.status != Status.APPROVED or p.approved_hash is None:
            raise ApprovalError("not approved")
        if p.payload_hash != p.approved_hash:
            p.status = Status.PENDING
            p.approved_hash = None
            self._repo.save(p)
            raise ApprovalError("payload changed after approval; approval voided")
        if not self._repo.claim(p):                   # someone else executed or changed it first
            raise ApprovalError("already executed or changed")
        p.status = Status.EXECUTED
        try:
            return writer(dict(p.payload))
        except Exception:
            p.status = Status.APPROVED                # the write failed: give the approval back, nothing saved
            self._repo.save(p)
            raise
