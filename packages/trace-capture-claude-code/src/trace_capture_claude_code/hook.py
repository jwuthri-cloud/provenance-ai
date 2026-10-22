"""`trace-claude-hook` — the Claude Code hook entrypoint.

Wired (by `trace init`) to PostToolUse / SessionStart / UserPromptSubmit. Reads
the hook JSON from stdin, dispatches by event, and forwards raw captures to the
daemon via trace-client. It NEVER blocks or fails Claude Code: every path is
wrapped and the process always exits 0 (docs/ARCHITECTURE.md §7).

The daemon — not this hook — decides the final source, computes the repo id /
relative path, classifies, and mints the canonical event. The hook just reports
what Claude did.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from trace_client import TraceClient

from . import session

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_from_transcript(transcript_path: str | None) -> str | None:
    if not transcript_path:
        return None
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        model = (obj.get("message") or {}).get("model") or obj.get("model")
        if model:
            return model
    return None


def _locate_span(file_text: str, needle: str) -> tuple[int, int] | None:
    """1-based (start_line, end_line) of the first occurrence of `needle`."""
    if not needle:
        return None
    idx = file_text.find(needle)
    if idx < 0:
        return None
    start = file_text[:idx].count("\n") + 1
    end = start + needle.count("\n")
    return start, end


def _line_count(text: str) -> int:
    return max(1, len(text.splitlines()))


def _captures_for_edit(tool: str, tool_input: dict, file_text: str, base: dict) -> list[dict]:
    caps: list[dict] = []
    if tool == "Write":
        content = tool_input.get("content", "")
        caps.append({**base, "content": content,
                     "content_range": {"start_line": 1, "end_line": _line_count(content)},
                     "operation": "create"})
    elif tool == "Edit":
        new = tool_input.get("new_string", "")
        span = _locate_span(file_text, new) or (1, _line_count(new))
        caps.append({**base, "content": new,
                     "content_range": {"start_line": span[0], "end_line": span[1]},
                     "operation": "replace" if tool_input.get("old_string") else "insert"})
    elif tool == "MultiEdit":
        for edit in tool_input.get("edits", []):
            new = edit.get("new_string", "")
            span = _locate_span(file_text, new) or (1, _line_count(new))
            caps.append({**base, "content": new,
                         "content_range": {"start_line": span[0], "end_line": span[1]},
                         "operation": "replace" if edit.get("old_string") else "insert"})
    elif tool == "NotebookEdit":
        # M1: notebooks get file-level provenance; cell-addressed ranges are a
        # spec decision deferred to M3 (docs/ARCHITECTURE.md §13).
        new = tool_input.get("new_source") or tool_input.get("new_string") or ""
        caps.append({**base, "content": new,
                     "content_range": {"start_line": 1, "end_line": _line_count(new)},
                     "operation": "replace"})
    return caps


def handle_post_tool_use(payload: dict, client: TraceClient) -> int:
    tool = payload.get("tool_name")
    if tool not in EDIT_TOOLS:
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0
    session_id = payload.get("session_id")
    sess = session.get(session_id) if session_id else {}
    model = sess.get("model") or _model_from_transcript(payload.get("transcript_path"))
    try:
        file_text = Path(file_path).read_text(encoding="utf-8")
    except Exception:
        file_text = ""

    base = {
        "abs_path": file_path,
        "raw_source_hint": "claude_code_tool_call",
        "model": model,
        "session_id": session_id,
        "prompt_hash": sess.get("prompt_hash"),
        "prompt_excerpt": sess.get("prompt_excerpt"),
        "timestamp": _now(),
        "tool_name": tool,
    }
    caps = _captures_for_edit(tool, tool_input, file_text, base)
    if caps:
        client.send_events(caps)
    return len(caps)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event = payload.get("hook_event_name") or payload.get("hook_event") or ""
    try:
        if event == "SessionStart":
            sid = payload.get("session_id")
            if sid:
                session.set_session(
                    sid,
                    model=_model_from_transcript(payload.get("transcript_path")),
                    cwd=payload.get("cwd"),
                )
        elif event == "UserPromptSubmit":
            sid = payload.get("session_id")
            prompt = payload.get("prompt", "")
            if sid and prompt:
                session.set_prompt(sid, prompt)
        elif event == "PostToolUse":
            handle_post_tool_use(payload, TraceClient())
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
