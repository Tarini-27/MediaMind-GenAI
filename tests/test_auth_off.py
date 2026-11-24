"""With login off (the config default while the team builds), the app works as before: everyone is demo."""
from fastapi.testclient import TestClient

from mediamind.api import auth
from mediamind.api.main import app


def test_login_off_means_demo_without_a_login_screen(monkeypatch):
    monkeypatch.delenv("MEDIAMIND_AUTH", raising=False)          # use the config, which says required: false
    c = TestClient(app)
    assert c.get("/auth/me").json() == {"user_id": "demo", "login": False}
    assert len(c.get("/items").json()) >= 10                     # demo's library, no user_id sent
    assert c.get("/items", params={"user_id": "other"}).json() != c.get("/items").json()   # scripts can still pick a user


def test_an_old_session_cookie_is_ignored_when_login_is_off(monkeypatch):
    monkeypatch.setenv("MEDIAMIND_AUTH", "on")
    c = TestClient(app)
    c.post("/auth/signup", json={"username": "oldsess", "password": "long-enough-pw"})
    monkeypatch.setenv("MEDIAMIND_AUTH", "off")
    assert c.get("/auth/me").json()["user_id"] == "demo"          # not the empty 'oldsess' library
    assert auth.auth_required() is False
