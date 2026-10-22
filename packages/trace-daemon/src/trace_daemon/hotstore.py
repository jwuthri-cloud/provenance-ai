"""SQLite WAL hot store — the durable source of truth for the last ~30 days.

This is the single-writer tier. Ingest accepts RAW CAPTURES from plugins, then
the daemon CLASSIFIES, mints the canonical (content-addressed) AuthorshipEvent
via trace-core, encrypts the prompt excerpt, extends the BLAKE3 hash chain, and
inserts idempotently keyed on event_id (docs/ARCHITECTURE.md §1, §7).
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from trace_core import (
    AuthorshipEvent,
    base_confidence,
    chain_hash,
    conf_after_edit,
)

from . import repoid
from .classify import classify
from .vault import Vault

# Source categories for aggregate analytics (the dashboard splits AI vs human vs generated).
AI_SOURCES = {
    "claude_code_tool_call", "cursor_agent", "cursor_autocomplete",
    "copilot_completion", "copilot_agent", "zed_agent", "ai_paste", "inferred",
}
HUMAN_SOURCES = {"human_keyboard", "human_paste"}
GENERATED_SOURCES = {"generated"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS repos (
    repo_id    TEXT PRIMARY KEY,
    root       TEXT,
    branch     TEXT,
    last_seen  TEXT
);
CREATE TABLE IF NOT EXISTS events (
    seq                  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id             TEXT UNIQUE NOT NULL,
    prev_hash            TEXT,
    chain_hash           TEXT NOT NULL,
    schema_version       INTEGER NOT NULL,
    timestamp            TEXT NOT NULL,
    received_at          TEXT NOT NULL,
    source               TEXT NOT NULL,
    model                TEXT,
    session_id           TEXT,
    prompt_hash          TEXT,
    prompt_excerpt_enc   BLOB,
    file_path            TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    content              TEXT,
    start_line           INTEGER NOT NULL,
    end_line             INTEGER NOT NULL,
    operation            TEXT NOT NULL,
    match_kind           TEXT,
    git_branch           TEXT,
    repo_id              TEXT,
    user_id              TEXT,
    confidence           REAL,
    classifier_confidence REAL,
    parent_event_id      TEXT,
    raw_json             TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_repo_file ON events (repo_id, file_path);
CREATE INDEX IF NOT EXISTS idx_events_session ON events (session_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HotStore:
    def __init__(self, db_path: Path, vault: Vault) -> None:
        self.db_path = db_path
        self.vault = vault
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- meta / chain -------------------------------------------------------
    def _get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def chain_head(self) -> str | None:
        return self._get_meta("chain_head")

    # ---- ingest -------------------------------------------------------------
    def ingest(self, raw_captures: list[dict]) -> dict:
        """Classify -> mint canonical event -> chain -> insert (idempotent).

        `raw_captures` are plugin payloads (see capture-plugin contract): they
        carry a raw_source_hint, content text, range, and metadata; the daemon
        decides the final source and builds the event.
        """
        accepted = 0
        repo_cache: dict[str, tuple] = {}  # parent dir -> (root, repo_id, branch); avoids per-event git calls
        with self._lock:
            head = self.chain_head()
            for raw in raw_captures:
                try:
                    event, content = self._mint(raw, repo_cache)
                except Exception:
                    continue  # one bad capture never blocks the batch
                # idempotency: skip if we already have this content-addressed id
                exists = self.conn.execute(
                    "SELECT 1 FROM events WHERE event_id=?", (event.event_id,)
                ).fetchone()
                if exists:
                    continue
                link = chain_hash(head, event.event_id, event.content_hash)
                self._insert(event, content, prev_hash=head, link=link)
                head = link
                accepted += 1
            if head is not None:
                self._set_meta("chain_head", head)
            self.conn.commit()
            durable_seq = self.conn.execute(
                "SELECT COALESCE(MAX(seq),0) AS s FROM events"
            ).fetchone()["s"]
        return {"accepted": accepted, "durable_seq": durable_seq, "chain_head": head}

    def _resolve_repo(self, raw: dict, repo_cache: dict) -> tuple[str, str | None, str | None]:
        """Turn the hook's absolute path into (relative file_path, repo_id, branch).

        Repo identity lives in the daemon (single authority) so plugins stay dumb;
        cached per parent dir to avoid a git subprocess per event."""
        abs_path = raw.get("abs_path")
        file_path = raw.get("file_path")
        repo_id = raw.get("repo_id")
        git_branch = raw.get("git_branch")
        if abs_path:
            p = Path(abs_path)
            parent = str(p.parent)
            if parent not in repo_cache:
                root = repoid.repo_root(p)
                rid_, branch_ = repoid.repo_id(p), repoid.current_branch(p)
                repo_cache[parent] = (root, rid_, branch_)
                self._upsert_repo(rid_, root, branch_)  # so the dashboard can read files back
            root, rid, branch = repo_cache[parent]
            if file_path is None:
                try:
                    file_path = str(p.resolve().relative_to(root)) if root else p.name
                except Exception:
                    file_path = p.name
            repo_id = repo_id or rid
            git_branch = git_branch or branch
        if file_path is None:
            raise ValueError("capture has neither file_path nor abs_path")
        return file_path, repo_id, git_branch

    def _mint(self, raw: dict, repo_cache: dict) -> tuple[AuthorshipEvent, str | None]:
        file_path, repo_id, git_branch = self._resolve_repo(raw, repo_cache)
        source, classifier_conf = classify(raw.get("raw_source_hint"), file_path)
        content = raw.get("content")
        edit_ratio = float(raw.get("edit_ratio") or 0.0)
        conf = conf_after_edit(base_confidence(source), edit_ratio)
        event = AuthorshipEvent.create(
            timestamp=raw.get("timestamp") or _now(),
            source=source,
            file_path=file_path,
            content=content,
            content_hash=raw.get("content_hash"),
            content_range=raw["content_range"],
            operation=raw.get("operation", "insert"),
            model=raw.get("model"),
            session_id=raw.get("session_id"),
            prompt_hash=raw.get("prompt_hash"),
            prompt_excerpt=raw.get("prompt_excerpt"),
            git_branch=git_branch,
            repo_id=repo_id,
            user_id=raw.get("user_id"),
            confidence=conf,
            classifier_confidence=classifier_conf,
            match_kind=raw.get("match_kind"),
        )
        return event, content

    def _insert(self, event: AuthorshipEvent, content: str | None, prev_hash: str | None, link: str) -> None:
        enc = self.vault.encrypt(event.prompt_excerpt)
        raw_json = event.model_dump_json()
        self.conn.execute(
            """INSERT INTO events (
                event_id, prev_hash, chain_hash, schema_version, timestamp, received_at,
                source, model, session_id, prompt_hash, prompt_excerpt_enc,
                file_path, content_hash, content, start_line, end_line, operation, match_kind,
                git_branch, repo_id, user_id, confidence, classifier_confidence,
                parent_event_id, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.event_id, prev_hash, link, event.schema_version, event.timestamp, _now(),
                event.source.value, event.model, event.session_id, event.prompt_hash, enc,
                event.file_path, event.content_hash, content,
                event.content_range.start_line, event.content_range.end_line,
                event.operation.value, event.match_kind.value if event.match_kind else None,
                event.git_branch, event.repo_id, event.user_id, event.confidence,
                event.classifier_confidence, event.parent_event_id, raw_json,
            ),
        )

    # ---- queries ------------------------------------------------------------
    def query_file(self, repo_id: str | None, file_path: str) -> list[dict]:
        if repo_id:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE repo_id=? AND file_path=? ORDER BY seq ASC",
                (repo_id, file_path),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE file_path=? ORDER BY seq ASC", (file_path,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["prompt_excerpt"] = self.vault.decrypt(r["prompt_excerpt_enc"])
            d.pop("prompt_excerpt_enc", None)
            out.append(d)
        return out

    def status(self) -> dict:
        c = self.conn
        total = c.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        by_source = {
            row["source"]: row["n"]
            for row in c.execute(
                "SELECT source, COUNT(*) AS n FROM events GROUP BY source ORDER BY n DESC"
            ).fetchall()
        }
        models = [
            row["model"]
            for row in c.execute(
                "SELECT DISTINCT model FROM events WHERE model IS NOT NULL"
            ).fetchall()
        ]
        repos = c.execute("SELECT COUNT(DISTINCT repo_id) AS n FROM events").fetchone()["n"]
        files = c.execute("SELECT COUNT(DISTINCT file_path) AS n FROM events").fetchone()["n"]
        sessions = c.execute(
            "SELECT COUNT(DISTINCT session_id) AS n FROM events WHERE session_id IS NOT NULL"
        ).fetchone()["n"]
        return {
            "events": total,
            "by_source": by_source,
            "models": models,
            "repos": repos,
            "files": files,
            "sessions": sessions,
            "chain_head": self.chain_head(),
        }

    # ---- repos (so the dashboard can resolve & read files back) -------------
    def _upsert_repo(self, repo_id: str | None, root, branch: str | None) -> None:
        if not repo_id or not root:
            return
        self.conn.execute(
            "INSERT INTO repos(repo_id, root, branch, last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(repo_id) DO UPDATE SET root=excluded.root, branch=excluded.branch, "
            "last_seen=excluded.last_seen",
            (repo_id, str(root), branch, _now()),
        )

    def get_repo_root(self, repo_id: str) -> str | None:
        row = self.conn.execute("SELECT root FROM repos WHERE repo_id=?", (repo_id,)).fetchone()
        return row["root"] if row else None

    # ---- analytics aggregates (consumed by the dashboard API) ---------------
    def overview(self) -> dict:
        c = self.conn
        by_source: dict[str, int] = {}
        for r in c.execute(
            "SELECT source, SUM(end_line-start_line+1) AS lines FROM events GROUP BY source"
        ).fetchall():
            by_source[r["source"]] = r["lines"] or 0
        total = sum(by_source.values())
        ai = sum(v for k, v in by_source.items() if k in AI_SOURCES)
        human = sum(v for k, v in by_source.items() if k in HUMAN_SOURCES)
        generated = sum(v for k, v in by_source.items() if k in GENERATED_SOURCES)
        recent = [
            {"file": r["file_path"], "source": r["source"], "model": r["model"],
             "lines": r["lines"], "ts": r["received_at"]}
            for r in c.execute(
                "SELECT file_path, source, model, received_at, (end_line-start_line+1) AS lines "
                "FROM events ORDER BY seq DESC LIMIT 12"
            ).fetchall()
        ]
        base = self.status()
        base.update({
            "total_lines": total, "by_source": by_source,
            "ai_lines": ai, "human_lines": human, "generated_lines": generated,
            "ai_pct": round(100 * ai / total, 1) if total else 0.0,
            "recent": recent,
        })
        return base

    def files(self) -> list[dict]:
        agg: dict[tuple, dict] = {}
        for r in self.conn.execute(
            "SELECT repo_id, file_path, source, model, (end_line-start_line+1) AS lines, received_at "
            "FROM events"
        ).fetchall():
            key = (r["repo_id"], r["file_path"])
            a = agg.setdefault(key, {"events": 0, "lines": 0, "by_source": {}, "models": {}, "last": ""})
            a["events"] += 1
            a["lines"] += r["lines"] or 0
            a["by_source"][r["source"]] = a["by_source"].get(r["source"], 0) + (r["lines"] or 0)
            if r["model"]:
                a["models"][r["model"]] = a["models"].get(r["model"], 0) + 1
            if (r["received_at"] or "") > a["last"]:
                a["last"] = r["received_at"]
        out = []
        for (rid, fp), a in agg.items():
            tot = sum(a["by_source"].values()) or 1
            ai = sum(v for k, v in a["by_source"].items() if k in AI_SOURCES)
            out.append({
                "repo_id": rid, "file": fp, "events": a["events"], "lines": a["lines"],
                "by_source": a["by_source"], "ai_pct": round(100 * ai / tot, 1),
                "top_model": max(a["models"], key=a["models"].get) if a["models"] else None,
                "flagged": (ai / tot) >= 0.8, "last_ts": a["last"],
            })
        out.sort(key=lambda x: (-x["ai_pct"], -x["lines"]))
        return out

    def sessions(self) -> list[dict]:
        agg: dict[str, dict] = {}
        for r in self.conn.execute(
            "SELECT session_id, model, prompt_excerpt_enc, file_path, "
            "(end_line-start_line+1) AS lines, received_at "
            "FROM events WHERE session_id IS NOT NULL ORDER BY seq"
        ).fetchall():
            s = agg.setdefault(r["session_id"], {
                "model": None, "prompt": None, "events": 0, "lines": 0,
                "files": set(), "first": r["received_at"], "last": r["received_at"],
            })
            s["events"] += 1
            s["lines"] += r["lines"] or 0
            s["files"].add(r["file_path"])
            if r["model"]:
                s["model"] = r["model"]
            pe = self.vault.decrypt(r["prompt_excerpt_enc"])
            if pe:
                s["prompt"] = pe
            s["last"] = r["received_at"]
        return [
            {"session_id": k, "model": v["model"], "prompt_excerpt": v["prompt"],
             "events": v["events"], "lines": v["lines"], "files": sorted(v["files"]),
             "first_ts": v["first"], "last_ts": v["last"]}
            for k, v in agg.items()
        ]

    def timeline(self) -> list[dict]:
        days: dict[str, dict] = {}
        for r in self.conn.execute(
            "SELECT substr(timestamp,1,10) AS day, source, "
            "SUM(end_line-start_line+1) AS lines FROM events GROUP BY day, source ORDER BY day"
        ).fetchall():
            d = days.setdefault(r["day"], {"day": r["day"], "by_source": {}, "lines": 0})
            d["by_source"][r["source"]] = r["lines"] or 0
            d["lines"] += r["lines"] or 0
        return list(days.values())

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
