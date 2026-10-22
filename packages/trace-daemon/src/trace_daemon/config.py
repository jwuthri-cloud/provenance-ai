"""Shared on-disk layout + daemon identity/token management.

TRACE_HOME (default ~/.trace) holds: db.sqlite, daemon.json (host/port/token/pid),
vault.key, spool/, sessions/, telemetry.jsonl, install_id.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
from pathlib import Path

VERSION = "0.1.0"
DEFAULT_PORT = 47100


def trace_home() -> Path:
    return Path(os.environ.get("TRACE_HOME", str(Path.home() / ".trace")))


def db_path() -> Path:
    return trace_home() / "db.sqlite"


def daemon_info_path() -> Path:
    return trace_home() / "daemon.json"


def vault_key_path() -> Path:
    return trace_home() / "vault.key"


def spool_dir() -> Path:
    return trace_home() / "spool"


def sessions_dir() -> Path:
    return trace_home() / "sessions"


def telemetry_path() -> Path:
    return trace_home() / "telemetry.jsonl"


def install_id_path() -> Path:
    return trace_home() / "install_id"


def ensure_home() -> Path:
    home = trace_home()
    home.mkdir(parents=True, exist_ok=True)
    try:
        home.chmod(0o700)
    except OSError:
        pass
    return home


def load_daemon_info() -> dict | None:
    try:
        return json.loads(daemon_info_path().read_text())
    except Exception:
        return None


def existing_token() -> str | None:
    info = load_daemon_info()
    return info.get("token") if info else None


def write_daemon_info(host: str, port: int, token: str, pid: int) -> None:
    ensure_home()
    p = daemon_info_path()
    p.write_text(
        json.dumps(
            {"host": host, "port": port, "token": token, "pid": pid, "version": VERSION},
            indent=2,
        )
    )
    try:
        p.chmod(0o600)
    except OSError:
        pass


def mint_token() -> str:
    return secrets.token_hex(16)


def telemetry_enabled() -> bool:
    """Product telemetry is OFF by default (local-first). Opt in via TRACE_TELEMETRY=1
    or a `telemetry: true` marker file. Even when on, it emits counts/flags only —
    never code, prompt, or path bytes (docs/ARCHITECTURE.md §7, review-fix)."""
    env = os.environ.get("TRACE_TELEMETRY", "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    return (trace_home() / "telemetry.on").exists()


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0
