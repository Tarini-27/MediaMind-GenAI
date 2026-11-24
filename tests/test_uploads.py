"""Upload path: pending folder, bytes bound into the approval, restricted edits, video validation."""
import io
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api import main
from mediamind.api.main import app
from mediamind.config import get_config
from mediamind.media import ffmpeg_status

client = TestClient(app)
U = {"user_id": "up"}
FFMPEG_OK, FFMPEG_WHY = ffmpeg_status()      # installed AND allowed to run (Windows may block it)
HAS_FFMPEG = FFMPEG_OK


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (40, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def propose(ct="image/png", name="pic.png", size=1000, **kw):
    r = client.post("/uploads/propose", json={"user_id": "up", "filename": name, "content_type": ct,
                                              "size_bytes": size, "title": "T", "category": "recipe", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def items():
    return client.get("/items", params=U).json()


def test_server_assigns_file_name_so_uploads_cannot_overwrite():
    p = propose(name="recipe_wrap.png")                       # same name as a seeded file
    assert p["payload"]["media"] != "recipe_wrap.png"
    assert p["payload"]["original_name"] == "recipe_wrap.png"


def test_unapproved_file_stays_out_of_public_media():
    p = propose()
    client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=png())
    assert not (main.MEDIA_DIR / p["payload"]["media"]).exists()
    assert client.get(f"/media/{p['payload']['media']}").status_code == 404
    assert (main.PENDING_DIR / p["proposal_id"] / p["payload"]["media"]).exists()


def test_approve_moves_file_and_saves_record():
    p = propose()
    client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=png())
    r = client.post(f"/approvals/{p['proposal_id']}/approve", json=U)
    assert r.status_code == 200
    assert (main.MEDIA_DIR / p["payload"]["media"]).exists()
    assert not (main.PENDING_DIR / p["proposal_id"]).exists()


def test_approve_without_file_is_refused():
    p = propose()
    assert client.post(f"/approvals/{p['proposal_id']}/approve", json=U).status_code == 409


def test_file_can_only_be_uploaded_once():
    p = propose()
    assert client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=png()).status_code == 200
    assert client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=png()).status_code == 409


def test_fake_image_bytes_rejected_and_cleaned_up():
    p = propose()
    r = client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=b"not really a png")
    assert r.status_code == 400
    assert not (main.PENDING_DIR / p["proposal_id"]).exists()
    assert all(x["id"] != p["proposal_id"] for x in client.get("/approvals", params=U).json())


def test_swapping_file_bytes_after_approval_is_caught():
    """Approval covers the exact bytes: replace the pending file and the save is refused."""
    p = propose()
    pid = p["proposal_id"]
    client.post(f"/uploads/{pid}/blob", params=U, content=png())
    before = len(items())
    main.gate.approve(pid, "up")
    (main.PENDING_DIR / pid / p["payload"]["media"]).write_bytes(b"swapped")
    with pytest.raises(main.ApprovalError):
        main.gate.execute(pid, "up", lambda payload: main._commit(pid, payload))
    assert len(items()) == before


def test_edit_cannot_change_server_owned_fields():
    p = propose()
    pid = p["proposal_id"]
    client.post(f"/uploads/{pid}/blob", params=U, content=png())
    e = client.post(f"/approvals/{pid}/edit", json={**U, "payload": {
        "title": "New title", "media": "recipe_wrap.png", "sha256": "0" * 64, "kind": "video"}}).json()
    assert e["payload"]["title"] == "New title"
    assert e["payload"]["media"] == p["payload"]["media"]
    assert e["payload"]["sha256"] != "0" * 64 and e["payload"]["kind"] == "image"


def test_reject_deletes_pending_file():
    p = propose()
    pid = p["proposal_id"]
    client.post(f"/uploads/{pid}/blob", params=U, content=png())
    client.post(f"/approvals/{pid}/reject", json=U)
    assert not (main.PENDING_DIR / pid).exists()


def test_preview_is_owner_only():
    p = propose()
    pid = p["proposal_id"]
    client.post(f"/uploads/{pid}/blob", params=U, content=png())
    assert client.get(f"/uploads/{pid}/preview", params=U).status_code == 200
    assert client.get(f"/uploads/{pid}/preview", params={"user_id": "someone"}).status_code == 409


# ---------------------------------------------------------------- video
def make_mp4(path: Path, seconds: int) -> bytes:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=blue:s=160x160:d={seconds}",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True)
    return path.read_bytes()


@pytest.mark.skipif(not HAS_FFMPEG, reason=f"ffmpeg unusable here: {FFMPEG_WHY}")
def test_video_upload_gets_thumbnail_and_plays_after_approval(tmp_path):
    data = make_mp4(tmp_path / "v.mp4", 2)
    p = propose(ct="video/mp4", name="clip.mp4", size=len(data))
    pid = p["proposal_id"]
    up = client.post(f"/uploads/{pid}/blob", params=U, content=data).json()
    assert up["duration_s"] == pytest.approx(2, abs=0.5)
    assert client.get(f"/uploads/{pid}/preview", params=U).headers["content-type"] == "image/jpeg"
    rec = client.post(f"/approvals/{pid}/approve", json=U).json()["record"]
    assert rec["kind"] == "video" and rec["thumb"].endswith("_thumb.jpg")
    assert client.get(f"/media/{rec['thumb']}").status_code == 200
    ranged = client.get(f"/media/{rec['media']}", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206                                  # seeking in the player works


@pytest.mark.skipif(not HAS_FFMPEG, reason=f"ffmpeg unusable here: {FFMPEG_WHY}")
def test_fake_video_rejected():
    p = propose(ct="video/mp4", name="x.mp4")
    r = client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=b"\x00" * 4000)
    assert r.status_code == 400 and "video" in r.json()["detail"]


@pytest.mark.skipif(not HAS_FFMPEG, reason=f"ffmpeg unusable here: {FFMPEG_WHY}")
def test_too_long_video_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config().guardrails, "max_video_seconds", 1)
    data = make_mp4(tmp_path / "long.mp4", 3)
    p = propose(ct="video/mp4", name="long.mp4", size=len(data))
    r = client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=data)
    assert r.status_code == 400 and "longer than" in r.json()["detail"]


def test_video_over_size_limit_rejected_at_propose():
    r = client.post("/uploads/propose", json={**U, "filename": "big.mp4", "content_type": "video/mp4",
                                              "size_bytes": 200 * 1024 * 1024, "title": "T", "category": "workout"})
    assert r.status_code == 400


def test_blocked_ffmpeg_gives_a_clear_message(monkeypatch):
    """If Windows blocks ffmpeg, a video upload is refused with the real reason, not 'unreadable video'."""
    from mediamind import media
    monkeypatch.setattr(media, "_STATUS", (False, "ffmpeg is installed but this machine refuses to run it"))
    p = propose(ct="video/mp4", name="clip.mp4", size=4000)
    r = client.post(f"/uploads/{p['proposal_id']}/blob", params=U, content=b"\x00" * 4000)
    assert r.status_code == 400 and "refuses to run" in r.json()["detail"]
