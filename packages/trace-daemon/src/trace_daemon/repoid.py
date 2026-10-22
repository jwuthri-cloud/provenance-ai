"""Canonical repo identity (review-fix, docs/ARCHITECTURE.md §7).

`repo_id` must be stable across clones, moves, and worktrees — so it is NEVER the
filesystem path. Preference order:
  1. `git:<root-commit-sha>` (stable across every clone of the same history)
  2. `local:<generated>` persisted in <root>/.trace/manifest.json (no git / no commits)
"""
from __future__ import annotations

import json
import secrets
import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str | None:
    # git needs a directory as cwd; callers often pass a file path
    cwd = cwd if cwd.is_dir() else cwd.parent
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def repo_root(path: Path) -> Path | None:
    top = _git(["rev-parse", "--show-toplevel"], path)
    return Path(top) if top else None


def current_branch(path: Path) -> str | None:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], path)


def _root_commit(path: Path) -> str | None:
    out = _git(["rev-list", "--max-parents=0", "HEAD"], path)
    if not out:
        return None
    # take the first root commit (oldest listed last; first line is fine + stable)
    return out.splitlines()[0].strip() or None


def _manifest_id(root: Path) -> str:
    manifest = root / ".trace" / "manifest.json"
    try:
        data = json.loads(manifest.read_text())
        if data.get("repo_id"):
            return data["repo_id"]
    except Exception:
        data = {}
    rid = "local:" + secrets.token_hex(8)
    data["repo_id"] = rid
    data.setdefault("version", 1)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=2))
    return rid


def repo_id(path: Path) -> str:
    """Resolve the canonical repo id for any path inside a repo."""
    base = path if path.is_dir() else path.parent
    root = repo_root(path) or base
    sha = _root_commit(root)
    if sha:
        return "git:" + sha
    return _manifest_id(root)
