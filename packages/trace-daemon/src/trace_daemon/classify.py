"""Daemon-side source classification (docs/ARCHITECTURE.md §7, cross-cutting decision).

ALL source classification lives here, not in plugins: plugins PROPOSE a
`raw_source_hint`; the daemon DECIDES the final source + classifier_confidence.
For Claude Code the hint (a real tool-call) is authoritative; the heuristic
edit-shape scoring matters for the M5 editors. `generated` is detected by path so
scaffolded/codegen output is never miscredited as human or AI.
"""
from __future__ import annotations

import fnmatch

from trace_core import Source

_KNOWN = {s.value for s in Source}

# Files that are generated/scaffolded — neither AI- nor human-authored.
GENERATED_GLOBS = [
    "**/package-lock.json",
    "**/yarn.lock",
    "**/pnpm-lock.yaml",
    "**/poetry.lock",
    "**/Cargo.lock",
    "**/go.sum",
    "**/uv.lock",
    "**/*.min.js",
    "**/*.min.css",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/*.pb.go",
    "**/migrations/*.py",
]


def is_generated_path(file_path: str) -> bool:
    norm = file_path.replace("\\", "/")
    base = norm.rsplit("/", 1)[-1]
    for pat in GENERATED_GLOBS:
        tail = pat.replace("**/", "")
        if fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(base, tail):
            return True
    return False


def classify(raw_source_hint: str | None, file_path: str) -> tuple[str, float]:
    """Return (final_source, classifier_confidence).

    Order: generated path > authoritative known hint > human_keyboard default.
    """
    if is_generated_path(file_path):
        return Source.generated.value, 0.95
    if raw_source_hint and raw_source_hint in _KNOWN:
        # a declared agent tool-call (e.g. claude_code_tool_call) is authoritative
        return raw_source_hint, 0.99
    # M1 default: anything unlabelled is treated as human-typed (low certainty).
    return Source.human_keyboard.value, 0.5
