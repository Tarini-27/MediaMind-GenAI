"""Database behaviour: persistence, per-user isolation, soft delete, and the SQLite-backed approval gate."""
import threading

import pytest

from mediamind import db
from mediamind.api import store
from mediamind.control.approval import ApprovalError, ApprovalGate
from mediamind.control.repos import SqliteProposalRepo

PAYLOAD = {"user_id": "u1", "media": "a.png", "title": "T", "category": "recipe"}


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """An empty, unseeded database for this test only."""
    monkeypatch.setenv("MEDIAMIND_DB", str(tmp_path / "t.sqlite"))
    db.init_db(seed=False)
    return tmp_path / "t.sqlite"


def gate():
    return ApprovalGate(SqliteProposalRepo())


# ---------------------------------------------------------------- records
def test_saved_item_survives_reconnect(fresh_db):
    rec = store.save_item({**PAYLOAD, "tags": ["x"], "fields": {"servings": 2}})
    again = store.get_item(rec["id"])               # fresh connection every call
    assert again["title"] == "T" and again["tags"] == ["x"] and again["fields"] == {"servings": 2}


def test_list_and_search_are_scoped_to_user(fresh_db):
    store.save_item({**PAYLOAD, "title": "paneer wrap"})
    store.save_item({**PAYLOAD, "user_id": "u2", "title": "paneer secret"})
    assert [r["title"] for r in store.list_items("u1")] == ["paneer wrap"]
    assert [r["title"] for r in store.search("u1", "paneer")] == ["paneer wrap"]
    assert store.list_items("nobody") == []


def test_soft_delete_hides_record_and_only_owner_can_delete(fresh_db):
    rec = store.save_item(PAYLOAD)
    assert store.soft_delete("u2", rec["id"]) is False       # not the owner
    assert store.get_item(rec["id"]) is not None
    assert store.soft_delete("u1", rec["id"]) is True
    assert store.get_item(rec["id"]) is None                  # cited-ID check treats it as absent
    assert store.list_items("u1") == []
    with db.connect() as c:                                    # but the row is still there (recoverable)
        assert c.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_seed_runs_once_and_only_into_empty_table(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DB", str(tmp_path / "s.sqlite"))
    db.init_db()
    db.init_db()                                              # second call must not duplicate
    with db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM items").fetchone()[0] == len(db.SEED_ITEMS) + len(db.SEED_VIDEOS)


def test_seed_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DB", str(tmp_path / "n.sqlite"))
    monkeypatch.setenv("MEDIAMIND_SEED", "0")
    db.init_db()
    with db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


# ---------------------------------------------------------------- approvals on SQLite
def test_pending_proposal_survives_restart(fresh_db):
    p = gate().propose("u1", "library.save", PAYLOAD)
    after_restart = gate()                                    # a brand new gate on the same database
    assert [x.id for x in after_restart.pending("u1")] == [p.id]
    assert after_restart.pending("u2") == []


def test_approval_survives_restart_and_still_writes_once(fresh_db):
    p = gate().propose("u1", "library.save", PAYLOAD)
    gate().approve(p.id, "u1")
    saved = gate().execute(p.id, "u1", store.save_item)       # different gate instance, same approval
    assert saved["title"] == "T"
    with pytest.raises(ApprovalError):
        gate().execute(p.id, "u1", store.save_item)           # executed state persisted: no replay
    assert len(store.list_items("u1")) == 1


def test_edit_voids_approval_in_database(fresh_db):
    g = gate()
    p = g.propose("u1", "library.save", PAYLOAD)
    g.approve(p.id, "u1")
    g.edit(p.id, "u1", {**PAYLOAD, "title": "Changed"})
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", store.save_item)
    assert store.list_items("u1") == []


def test_tampering_with_stored_payload_is_caught(fresh_db):
    """Someone edits the proposals row directly after approval: the hash is recomputed and no longer matches."""
    g = gate()
    p = g.propose("u1", "library.save", PAYLOAD)
    g.approve(p.id, "u1")
    with db.connect() as c:
        c.execute("UPDATE proposals SET payload = ? WHERE id = ?",
                  ('{"user_id":"u1","media":"a.png","title":"HACKED","category":"recipe"}', p.id))
    with pytest.raises(ApprovalError):
        g.execute(p.id, "u1", store.save_item)
    assert store.list_items("u1") == []


def test_concurrent_execute_writes_exactly_once(fresh_db):
    """Double click / retry race: only one caller may win the claim."""
    g = gate()
    p = g.propose("u1", "library.save", PAYLOAD)
    g.approve(p.id, "u1")
    results = []

    def run():
        try:
            g.execute(p.id, "u1", store.save_item)
            results.append("ok")
        except ApprovalError:
            results.append("refused")

    threads = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 1
    assert len(store.list_items("u1")) == 1


def test_failed_write_gives_the_approval_back(fresh_db):
    g = gate()
    p = g.propose("u1", "library.save", PAYLOAD)
    g.approve(p.id, "u1")

    def boom(_):
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        g.execute(p.id, "u1", boom)
    assert store.list_items("u1") == []
    g.execute(p.id, "u1", store.save_item)                    # retry works, approval was not consumed
    assert len(store.list_items("u1")) == 1


def test_other_user_cannot_touch_proposal_in_database(fresh_db):
    g = gate()
    p = g.propose("u1", "library.save", PAYLOAD)
    with pytest.raises(ApprovalError):
        g.approve(p.id, "u2")
