"""Deleting an item is a write: it waits for approval, is soft (recoverable), and only the owner can do it."""
from fastapi.testclient import TestClient

from mediamind.api import store
from mediamind.api.main import app

client = TestClient(app)


def fresh(user="demo", title="to delete"):
    return store.save_item({"user_id": user, "media": "x.png", "category": "other", "title": title})["id"]


def ids(user="demo"):
    return {i["id"] for i in client.get("/items", params={"user_id": user}).json()}


def propose(item_id, user="demo"):
    return client.post(f"/items/{item_id}/delete", json={"user_id": user})


def decide(pid, verb="approve", user="demo"):
    return client.post(f"/approvals/{pid}/{verb}", json={"user_id": user})


def test_nothing_is_deleted_until_approved():
    rid = fresh()
    r = propose(rid).json()
    assert r["status"] == "pending" and r["payload"]["title"] == "to delete"
    assert rid in ids()
    ok = decide(r["proposal_id"])
    assert ok.status_code == 200 and ok.json()["status"] == "deleted"
    assert rid not in ids()


def test_delete_is_soft_and_reversible_in_the_db():
    rid = fresh()
    decide(propose(rid).json()["proposal_id"])
    from mediamind.db import connect
    with connect() as c:
        row = c.execute("SELECT deleted_at FROM items WHERE id = ?", (rid,)).fetchone()
    assert row is not None and row["deleted_at"]          # row kept, only hidden


def test_reject_keeps_the_item():
    rid = fresh()
    decide(propose(rid).json()["proposal_id"], "reject")
    assert rid in ids()


def test_cannot_delete_someone_elses_item():
    rid = fresh(user="alice")
    assert propose(rid, user="demo").status_code == 404   # looks the same as a missing item
    assert propose("nope", user="demo").status_code == 404
    assert rid in ids("alice")


def test_other_user_cannot_approve_my_delete():
    rid = fresh()
    pid = propose(rid).json()["proposal_id"]
    assert decide(pid, user="mallory").status_code == 409
    assert rid in ids()


def test_delete_cannot_be_edited_into_another_item():
    rid, other = fresh(), fresh(title="keep me")
    pid = propose(rid).json()["proposal_id"]
    client.post(f"/approvals/{pid}/edit", json={"user_id": "demo", "payload": {"item_id": other}})
    decide(pid)
    assert other in ids() and rid not in ids()


def test_approval_is_single_use_and_second_delete_fails_cleanly():
    rid = fresh()
    a, b = propose(rid).json()["proposal_id"], propose(rid).json()["proposal_id"]
    assert decide(a).status_code == 200
    assert decide(a).status_code == 409                  # replay
    assert decide(b).status_code == 409                  # already gone; nothing else touched


def test_deleted_item_leaves_search_and_collections():
    rid = fresh(title="zebra unique")
    client.post("/collections/propose", json={"user_id": "demo", "name": "zebras", "item_ids": [rid]})
    pid = [p for p in client.get("/approvals", params={"user_id": "demo"}).json()
           if p["action"] == "library.collect" and p["payload"]["name"] == "zebras"][0]["id"]
    decide(pid)
    decide(propose(rid).json()["proposal_id"])
    assert all(r["id"] != rid for r in store.search("demo", "zebra unique"))
    assert {c["name"]: c["count"] for c in client.get("/collections", params={"user_id": "demo"}).json()}["zebras"] == 0
