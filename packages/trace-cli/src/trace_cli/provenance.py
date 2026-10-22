"""Provenance access for the CLI.

M1: read the hot store directly (the daemon is only needed for ingest). This is
the fetch layer beneath the shared blame resolver; in M2 the ProvenanceSource
strategy gains a notes fallback so blame works on a fresh clone with no daemon
and no hot store (docs/ARCHITECTURE.md §6).
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from trace_daemon import config, repoid
from trace_daemon.hotstore import HotStore
from trace_daemon.tracker import compute_blame, summarize
from trace_daemon.vault import Vault


def open_store() -> HotStore:
    config.ensure_home()
    return HotStore(config.db_path(), Vault(config.vault_key_path()))


def _rel(abspath: Path) -> tuple[str, str | None]:
    root = repoid.repo_root(abspath)
    rid = repoid.repo_id(abspath)
    if root:
        try:
            return str(abspath.relative_to(root)), rid
        except ValueError:
            pass
    return abspath.name, rid


def blame_file(abspath: Path, range_filter: tuple[int, int] | None = None) -> dict:
    store = open_store()
    try:
        rel, rid = _rel(abspath)
        rows = store.query_file(rid, rel)
        text = abspath.read_text(encoding="utf-8")
        result = compute_blame(rows, text, range_filter)
        result["file"] = rel
        result["repo_id"] = rid
        result["summary"] = summarize(result["spans"])
        result["event_count"] = len(rows)
        return result
    finally:
        store.close()


def repo_summary(path: Path) -> dict:
    store = open_store()
    try:
        rid = repoid.repo_id(path)
        branch = repoid.current_branch(path)
        rows = store.conn.execute(
            """SELECT source, model, start_line, end_line, session_id
               FROM events WHERE repo_id=?""",
            (rid,),
        ).fetchall()
        by_source: dict[str, int] = {}
        models: set[str] = set()
        sessions: set[str] = set()
        for r in rows:
            lines = max(1, r["end_line"] - r["start_line"] + 1)
            by_source[r["source"]] = by_source.get(r["source"], 0) + lines
            if r["model"]:
                models.add(r["model"])
            if r["session_id"]:
                sessions.add(r["session_id"])
        total = sum(by_source.values()) or 1
        return {
            "repo_id": rid,
            "branch": branch,
            "events": len(rows),
            "total_lines": sum(by_source.values()),
            "by_source": by_source,
            "pct": {k: round(100 * v / total, 1) for k, v in by_source.items()},
            "models": sorted(models),
            "sessions": len(sessions),
        }
    finally:
        store.close()


def daemon_health() -> dict | None:
    info = config.load_daemon_info()
    if not info or not info.get("port"):
        return None
    try:
        url = f"http://{info.get('host', '127.0.0.1')}:{info['port']}/healthz"
        with urllib.request.urlopen(url, timeout=0.3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None
