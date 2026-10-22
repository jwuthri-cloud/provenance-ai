"""Opt-in product telemetry (review-fix, docs/ARCHITECTURE.md §7, §12).

The "measurability product" must be able to measure its own activation — but
local-first. So this emitter is OFF by default, gated by an explicit opt-in, and
emits COUNTS/FLAGS ONLY (an allowlist) — never code, prompts, file paths, or repo
names. In M1 it writes a local JSONL; cloud forwarding is M4 and opt-in again.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import config

# Hard allowlist of property keys — anything not here is dropped, so no content,
# path, or prompt bytes can leak into telemetry even by accident.
SAFE_KEYS = {"count", "source_count", "file_count", "ms_bucket", "command", "phase", "ok"}


def install_id() -> str:
    p = config.install_id_path()
    try:
        return p.read_text().strip()
    except Exception:
        iid = "ins_" + uuid.uuid4().hex[:16]
        try:
            config.ensure_home()
            p.write_text(iid)
            p.chmod(0o600)
        except Exception:
            pass
        return iid


def emit(event_name: str, **props) -> None:
    if not config.telemetry_enabled():
        return
    safe = {k: v for k, v in props.items() if k in SAFE_KEYS}
    rec = {
        "event": event_name,
        "ts": datetime.now(timezone.utc).isoformat(),
        "install_id": install_id(),
        **safe,
    }
    try:
        config.ensure_home()
        with config.telemetry_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass
