"""Merge trace's hooks into a Claude Code settings.json without clobbering others.

`trace init` calls this against the PROJECT's .claude/settings.json (never the
user's global config silently). Idempotent: re-running does not duplicate hooks.
"""
from __future__ import annotations

import json
from pathlib import Path

HOOK_CMD = "trace-claude-hook"


def hooks_block() -> dict:
    one = [{"hooks": [{"type": "command", "command": HOOK_CMD}]}]
    return {
        "PostToolUse": [
            {"matcher": "Edit|Write|MultiEdit|NotebookEdit",
             "hooks": [{"type": "command", "command": HOOK_CMD}]}
        ],
        "SessionStart": one,
        "UserPromptSubmit": one,
    }


def _has_trace_hook(entries: list) -> bool:
    for entry in entries:
        for h in entry.get("hooks", []):
            if h.get("command") == HOOK_CMD:
                return True
    return False


def merge_into_settings(settings_path: Path) -> dict:
    """Add trace hooks to settings_path. Returns {added: [...], already: [...]}."""
    try:
        settings = json.loads(settings_path.read_text())
    except Exception:
        settings = {}
    hooks = settings.setdefault("hooks", {})
    added, already = [], []
    for event, entries in hooks_block().items():
        existing = hooks.setdefault(event, [])
        if _has_trace_hook(existing):
            already.append(event)
        else:
            existing.extend(entries)
            added.append(event)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return {"added": added, "already": already, "path": str(settings_path)}
