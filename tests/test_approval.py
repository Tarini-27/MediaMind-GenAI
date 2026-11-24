import pytest

from mediamind.control.approval import ApprovalError, ApprovalGate, payload_hash

PAYLOAD = {"title": "No-oven paneer wrap", "category": "recipe"}


def make():
    g = ApprovalGate()
    return g, g.propose("u1", "library.save", PAYLOAD)


def test_approve_then_write_succeeds():
    g, p = make()
    g.approve(p.id, "u1")
    written = []
    g.execute(p.id, "u1", written.append)
    assert written == [PAYLOAD]


def test_write_without_approval_fails():
    g, p = make()
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", lambda x: None)


def test_edit_voids_earlier_approval():
    """The live demo: approve, then edit -> old approval no longer works."""
    g, p = make()
    g.approve(p.id, "u1")
    g.edit(p.id, "u1", {**PAYLOAD, "title": "Changed title"})
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", lambda x: None)
    # re-approving the new payload works
    g.approve(p.id, "u1")
    out = []
    g.execute(p.id, "u1", out.append)
    assert out[0]["title"] == "Changed title"


def test_tampering_after_approval_is_caught_at_execute():
    g, p = make()
    g.approve(p.id, "u1")
    p.payload["title"] = "tampered"            # mutate behind the gate's back
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", lambda x: None)


def test_reject_writes_nothing():
    g, p = make()
    g.reject(p.id, "u1")
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", lambda x: None)


def test_approval_is_single_use():
    g, p = make()
    g.approve(p.id, "u1")
    g.execute(p.id, "u1", lambda x: None)
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", lambda x: None)


def test_other_user_cannot_see_or_approve():
    g, p = make()
    with pytest.raises(ApprovalError):
        g.approve(p.id, "u2")
    assert g.pending("u2") == []


def test_hash_ignores_key_order_but_not_values():
    a = payload_hash("u1", "x", {"a": 1, "b": 2})
    assert a == payload_hash("u1", "x", {"b": 2, "a": 1})
    assert a != payload_hash("u1", "x", {"a": 1, "b": 3})
    assert a != payload_hash("u2", "x", {"a": 1, "b": 2})
