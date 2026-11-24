"""ffprobe / ffmpeg helpers for video uploads. Arguments are passed as a list (never a shell string),
with timeouts, so a hostile file name or file cannot inject commands or hang the API.

Role 2 builds the real video processing (faster-whisper transcript, PySceneDetect frames) on top of
these files; this module only validates uploads and makes a thumbnail for the gallery.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


_STATUS: tuple[bool, str] | None = None


def ffmpeg_status() -> tuple[bool, str]:
    """(usable, reason). Checks that ffmpeg and ffprobe exist AND can actually run: on some Windows
    machines Application Control lets them install but blocks them from starting. Cached per process."""
    global _STATUS
    if _STATUS is None:
        missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
        if missing:
            _STATUS = (False, f"{' and '.join(missing)} not found on PATH; install ffmpeg and open a new terminal")
        else:
            try:
                for tool in ("ffmpeg", "ffprobe"):
                    subprocess.run([tool, "-version"], capture_output=True, timeout=15, check=True)
                _STATUS = (True, "ok")
            except OSError as e:
                _STATUS = (False, f"ffmpeg is installed but this machine refuses to run it ({e}). "
                                  "Run the backend in Docker or WSL for video")
            except subprocess.SubprocessError as e:
                _STATUS = (False, f"ffmpeg did not run correctly: {e}")
    return _STATUS


def ffmpeg_available() -> bool:
    return ffmpeg_status()[0]


def probe(path: Path) -> dict | None:
    """Return {'duration': seconds, 'has_video': bool, 'format': str}, or None if it is not a readable media file."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
        info = json.loads(out)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return None
    streams = info.get("streams", [])
    fmt = info.get("format", {})
    try:
        duration = float(fmt.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {"duration": duration,
            "has_video": any(s.get("codec_type") == "video" for s in streams),
            "format": fmt.get("format_name", "")}


def make_thumbnail(video: Path, out: Path) -> bool:
    """Grab one frame (at 1s, or the first frame for very short clips) as a JPEG."""
    for at in ("1", "0"):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", at, "-i", str(video), "-frames:v", "1",
                 "-vf", "scale=720:-2", str(out)],
                capture_output=True, timeout=30, check=True,
            )
            if out.exists() and out.stat().st_size > 0:
                return True
        except (subprocess.SubprocessError, OSError):
            continue
    return False
