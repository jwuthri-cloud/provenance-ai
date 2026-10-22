#!/usr/bin/env python3
"""Seed a realistic provenance dataset so the dashboard has something to show.

Creates a self-contained sample repo under TRACE_HOME/sample_repo and ingests a
mix of AI (two models), human, autocomplete, and generated authorship across
several files — including one file a human hand-edited after the AI wrote it.

    TRACE_HOME=/tmp/trace-demo uv run python scripts/seed_demo.py
    TRACE_HOME=/tmp/trace-demo uv run trace-daemon            # terminal 2
    cd apps/dashboard && TRACE_HOME=/tmp/trace-demo npm run dev
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from trace_daemon.hotstore import HotStore
from trace_daemon.vault import Vault

AUTH = '''import time

_buckets: dict[str, list[float]] = {}


def rate_limit(key, limit=5, window=60):
    now = time.time()
    bucket = _buckets.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def validate_login(payload):
    if not payload.get("email"):
        raise ValueError("email required")
    if len(payload.get("password", "")) < 8:
        raise ValueError("password too short")
    return True
'''

API = '''from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/users")
_users: dict[int, dict] = {}


@router.get("/{uid}")
def get_user(uid: int):
    if uid not in _users:
        raise HTTPException(404, "not found")
    return _users[uid]


@router.post("/")
def create_user(user: dict):
    uid = max(_users) + 1 if _users else 1
    _users[uid] = user
    return {"id": uid, **user}
'''

UTILS = '''import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def truncate(text, n=80):
    return text if len(text) <= n else text[: n - 1] + "…"
'''

README = "# sample\n\nA demo repo used to seed trace provenance.\n"
LOCK = '{\n  "name": "sample",\n  "lockfileVersion": 3,\n  "packages": {}\n}\n'


def slice_lines(text: str, start: int, end: int) -> str:
    return "\n".join(text.splitlines()[start - 1:end]) + "\n"


def main() -> int:
    home = Path(os.environ.get("TRACE_HOME") or tempfile.mkdtemp(prefix="trace-demo-"))
    home.mkdir(parents=True, exist_ok=True)
    repo = home / "sample_repo"
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=False)

    files = {"src/auth.py": AUTH, "src/api.py": API, "src/utils.py": UTILS,
             "README.md": README, "package-lock.json": LOCK}
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def cap(rel, start, end, hint, model, session, prompt, ts):
        return {
            "abs_path": str(repo / rel),
            "content": slice_lines(files[rel], start, end),
            "content_range": {"start_line": start, "end_line": end},
            "raw_source_hint": hint, "model": model, "session_id": session,
            "prompt_excerpt": prompt,
            "prompt_hash": ("sha256:" + str(abs(hash(prompt)))) if prompt else None,
            "operation": "insert", "timestamp": ts,
        }

    d1, d2, d3 = "2026-05-30", "2026-05-31", "2026-06-01"
    captures = [
        # auth.py — Claude Sonnet wrote the whole file across two declarations
        cap("src/auth.py", 1, 13, "claude_code_tool_call", "claude-sonnet-4-5",
            "sess_auth", "add rate limiting to the login endpoint", f"{d1}T10:01:00Z"),
        cap("src/auth.py", 16, 22, "claude_code_tool_call", "claude-sonnet-4-5",
            "sess_auth", "add input validation to login", f"{d1}T10:04:00Z"),
        # api.py — Claude Opus wrote the user CRUD endpoints
        cap("src/api.py", 1, 21, "claude_code_tool_call", "claude-opus-4-8",
            "sess_api", "build REST endpoints for user CRUD", f"{d2}T14:20:00Z"),
        # utils.py — human typed slugify, autocomplete suggested truncate
        cap("src/utils.py", 1, 5, "human_keyboard", None, None, None, f"{d2}T16:00:00Z"),
        cap("src/utils.py", 7, 9, "cursor_autocomplete", "claude-sonnet-4-5",
            "sess_utils", "add a truncate helper", f"{d3}T09:30:00Z"),
        # README — human; package-lock — generated
        cap("README.md", 1, 3, "human_keyboard", None, None, None, f"{d1}T09:00:00Z"),
        cap("package-lock.json", 1, 5, "generated", None, None, None, f"{d2}T14:25:00Z"),
    ]

    store = HotStore(home / "db.sqlite", Vault(home / "vault.key"))
    res = store.ingest(captures)
    store.close()

    # a human hand-edits the AI's rate limiter after the fact
    auth_path = repo / "src/auth.py"
    auth_path.write_text(auth_path.read_text().replace("limit=5", "limit=10  # raised by hand"))

    print(f"seeded {res['accepted']} events into {home/'db.sqlite'}")
    print(f"TRACE_HOME={home}")
    print("\nNext:")
    print(f"  TRACE_HOME={home} uv run trace-daemon")
    print(f"  cd apps/dashboard && TRACE_HOME={home} npm run dev   # http://localhost:3000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
