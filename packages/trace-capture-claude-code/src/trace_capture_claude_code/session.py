"""Per-session registry: caches model + the originating prompt across hook events.

PostToolUse does not carry the model or the prompt, so we join them by
session_id: SessionStart caches the model (from the transcript), UserPromptSubmit
caches the latest prompt (redacted + hashed). The write event then links to the
prompt that drove it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from trace_client import trace_home

# Tier-1 redaction: mask obvious secrets BEFORE any excerpt is stored
# (docs/ARCHITECTURE.md §8). M2 adds detect-secrets/gitleaks.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
]


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _dir() -> Path:
    d = trace_home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", session_id)
    return _dir() / f"{safe}.json"


def load(session_id: str) -> dict:
    try:
        return json.loads(_path(session_id).read_text())
    except Exception:
        return {}


def _save(session_id: str, data: dict) -> None:
    try:
        _path(session_id).write_text(json.dumps(data))
    except Exception:
        pass


def set_session(session_id: str, model: str | None = None, cwd: str | None = None) -> None:
    d = load(session_id)
    if model:
        d["model"] = model
    if cwd:
        d["cwd"] = cwd
    _save(session_id, d)


def set_prompt(session_id: str, prompt: str) -> None:
    d = load(session_id)
    d["prompt_hash"] = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    first = prompt.strip().splitlines()[0] if prompt.strip() else ""
    d["prompt_excerpt"] = redact(first)[:140]
    _save(session_id, d)


def get(session_id: str) -> dict:
    return load(session_id)
