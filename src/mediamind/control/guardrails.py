"""Input and output guardrails as plain, unit-testable functions.

These are the cheap rule layers. Prompt Guard 2 / Llama Guard 4 get added as extra layers later
(`detect_injection` is where a classifier call would plug in). Several layers, not one filter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

# ---------------------------------------------------------------- input: PII masking
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?\d{10}(?!\d)")),
]


def mask_pii(text: str) -> str:
    """Replace PII with [TYPE] placeholders. Used before text reaches a model, trace or log."""
    for label, pat in _PII_PATTERNS:
        text = pat.sub(f"[{label}]", text)
    return text


# Secrets must never reach a log or trace, even if a key ends up in a prompt, tool argument or error.
_SECRET_PATTERNS = [
    re.compile(r"sk-or-v\d-[A-Za-z0-9]{20,}"),                      # OpenRouter
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),                          # OpenAI-style
    re.compile(r"\b(?:pk|sk)-lf-[A-Za-z0-9-]{8,}"),                  # Langfuse
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{16,}=*"),
    re.compile(r"(?i)((?:api[_-]?key|secret|token|password)\s*[=:]\s*)[\"']?[^\s\"',;]{8,}"),
]


def scrub(text: str) -> str:
    """mask_pii plus secret removal. Use for anything written to logs or traces."""
    text = mask_pii(text)
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if pat.groups else "") + "[SECRET]", text)
    return text


# ---------------------------------------------------------------- input: injection
_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any |the )?(previous|prior|above)",
    r"you are now\b",
    r"\bsystem\s*:",
    r"new instructions?\s*:",
    r"(delete|erase|wipe) (all|every) (my )?(records?|items?|data|collections?)",
    r"note to (the )?ai",
    r"reveal (your |the )?(system )?prompt",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


@dataclass
class ScanResult:
    flagged: bool
    reason: str | None = None


def detect_injection(text: str, classifier: Callable[[str], bool] | None = None) -> ScanResult:
    """Scan user text AND extracted OCR/transcript text. Screenshots are the real attack path.

    `classifier` is an optional extra layer (e.g. Prompt Guard 2) returning True when malicious.
    """
    m = _INJECTION_RE.search(text or "")
    if m:
        return ScanResult(True, f"rule match: {m.group(0)[:40]!r}")
    if classifier and classifier(text):
        return ScanResult(True, "classifier flagged")
    return ScanResult(False)


# ---------------------------------------------------------------- input: file checks
@dataclass
class UploadCheck:
    ok: bool
    reason: str | None = None


def check_upload(filename: str, content_type: str, size_bytes: int,
                 allowed_types: Iterable[str], max_mb: int) -> UploadCheck:
    if content_type not in set(allowed_types):
        return UploadCheck(False, f"type {content_type!r} not allowed")
    if size_bytes <= 0:
        return UploadCheck(False, "empty file")
    if size_bytes > max_mb * 1024 * 1024:
        return UploadCheck(False, f"file larger than {max_mb} MB")
    if re.search(r"[\\/]|\.\.", filename):
        return UploadCheck(False, "unsafe filename")
    return UploadCheck(True)


def check_image_bytes(data: bytes) -> UploadCheck:
    """The declared type is only a claim: make sure the bytes really are an image."""
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(data)) as im:
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return UploadCheck(False, "file is not a valid image")
    return UploadCheck(True)


def check_video(info: dict | None, max_seconds: int) -> UploadCheck:
    """`info` comes from media.probe(). None means ffprobe could not read it."""
    if info is None:
        return UploadCheck(False, "file is not a readable video")
    if not info["has_video"]:
        return UploadCheck(False, "no video stream found")
    if info["duration"] <= 0:
        return UploadCheck(False, "could not read video duration")
    if info["duration"] > max_seconds:
        return UploadCheck(False, f"video longer than {max_seconds} s")
    return UploadCheck(True)


# ---------------------------------------------------------------- output: citations
def check_citations(cited_ids: Iterable[str], user_id: str,
                    lookup: Callable[[str], dict | None]) -> list[str]:
    """Every cited record must exist AND belong to the caller. Returns a list of violations.

    `lookup(record_id)` returns the record dict (with 'user_id') or None.
    """
    violations = []
    for rid in cited_ids:
        rec = lookup(rid)
        if rec is None:
            violations.append(f"{rid}: does not exist")
        elif rec.get("user_id") != user_id:
            violations.append(f"{rid}: belongs to another user")
    return violations
