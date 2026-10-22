"""FastAPI ingest + query/control server (127.0.0.1 only).

Ingest authenticity (review-fix): every request must carry the per-daemon token
AND a loopback Host header (defeats DNS-rebinding against 127.0.0.1). The token
file is 0600; only local processes that can read it can post events. The hash
chain proves integrity AFTER capture; the token provides authenticity AT capture.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from . import config, repoid, telemetry
from .hotstore import HotStore
from .tracker import compute_blame, summarize

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _reconstruct(rows: list[dict]) -> str:
    """Best-effort file text from stored authored content, for events whose file
    is no longer on disk (e.g. demo/seeded data or a cleaned worktree)."""
    if not rows:
        return ""
    max_line = max(r["end_line"] for r in rows)
    buf = [""] * max_line
    for r in rows:  # ascending seq -> later events override earlier
        content = r.get("content")
        if not content:
            continue
        for i, ln in enumerate(content.splitlines()):
            idx = r["start_line"] - 1 + i
            if 0 <= idx < max_line:
                buf[idx] = ln
    return "\n".join(buf)


def _parse_body(body: bytes) -> list[dict]:
    text = body.decode("utf-8").strip()
    if not text:
        return []
    # try NDJSON first (the wire format), then a JSON array
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]


def _rel_path(abspath: Path) -> tuple[str, str | None]:
    root = repoid.repo_root(abspath)
    rid = repoid.repo_id(abspath)
    if root:
        try:
            return str(abspath.relative_to(root)), rid
        except ValueError:
            pass
    return abspath.name, rid


def create_app(store: HotStore, token: str) -> FastAPI:
    app = FastAPI(title="trace daemon", version=config.VERSION)
    # the dashboard may call read endpoints from the browser; loopback dev origins only
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def _auth(x_trace_token: str | None, host: str | None) -> None:
        host = (host or "").split(":")[0]
        if host and host not in _LOOPBACK_HOSTS:
            raise HTTPException(status_code=403, detail="non-loopback host rejected")
        if not token or x_trace_token != token:
            raise HTTPException(status_code=401, detail="invalid or missing token")

    @app.post("/ingest")
    async def ingest(
        request: Request,
        x_trace_token: str | None = Header(default=None),
    ) -> dict:
        _auth(x_trace_token, request.headers.get("host"))
        raws = _parse_body(await request.body())
        result = store.ingest(raws)
        telemetry.emit("events_ingested", count=result["accepted"])
        return result

    @app.get("/status")
    def status() -> dict:
        st = store.status()
        st["version"] = config.VERSION
        st["db"] = str(store.db_path)
        st["telemetry"] = config.telemetry_enabled()
        return st

    @app.get("/blame")
    def blame(path: str, repo_id: str | None = None) -> dict:
        abspath = Path(path).expanduser().resolve()
        try:
            text = abspath.read_text()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=f"cannot read file: {exc}")
        rel, rid = _rel_path(abspath)
        rows = store.query_file(repo_id or rid, rel)
        result = compute_blame(rows, text)
        result["file"] = rel
        result["repo_id"] = repo_id or rid
        result["summary"] = summarize(result["spans"])
        return result

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "version": config.VERSION}

    # ---- dashboard analytics API (read-only, loopback) ----------------------
    @app.get("/api/overview")
    def api_overview() -> dict:
        ov = store.overview()
        ov["version"] = config.VERSION
        return ov

    @app.get("/api/files")
    def api_files() -> dict:
        return {"files": store.files()}

    @app.get("/api/sessions")
    def api_sessions() -> dict:
        return {"sessions": store.sessions()}

    @app.get("/api/timeline")
    def api_timeline() -> dict:
        return {"timeline": store.timeline()}

    @app.get("/api/file")
    def api_file(repo_id: str, path: str) -> dict:
        rows = store.query_file(repo_id, path)
        if not rows:
            raise HTTPException(status_code=404, detail="no provenance for this file")
        root = store.get_repo_root(repo_id)
        text = None
        if root:
            try:
                text = (Path(root) / path).read_text()
            except Exception:
                text = None
        on_disk = text is not None
        if text is None:
            text = _reconstruct(rows)
        result = compute_blame(rows, text)
        result["file"] = path
        result["repo_id"] = repo_id
        result["on_disk"] = on_disk
        result["text"] = text
        result["summary"] = summarize(result["spans"])
        return result

    return app
