"""Blame computation + lightweight human-edit detection (M1, hot-only).

M1 scope is honest: attribution maps current working-tree lines to the most
recent event covering them, and human-edit ratio is detected by diffing the
event's authored text against the current span. The AST chunk tracker that
follows provenance across COMMITS/refactors (and the canonical HumanEditDetector
at chunk scope) is M2 — see docs/ARCHITECTURE.md §4. This shared resolver is the
M1 stand-in for the single BlameResolver that moves to trace-core in M2.
"""
from __future__ import annotations

import difflib

from trace_core import Source, badge, base_confidence, conf_after_edit


def _author_label(source: str, model: str | None) -> str:
    if source == Source.human_keyboard.value:
        return "you (keyboard)"
    if source == Source.human_paste.value:
        return "you (paste)"
    if source == Source.generated.value:
        return "generated"
    if model:
        return f"{model} ({source})"
    return source


def _span_from_row(start: int, end: int, row: dict | None, lines: list[str]) -> dict:
    if row is None:
        return {
            "start": start, "end": end, "source": Source.human_keyboard.value,
            "author": "you (keyboard)", "model": None, "confidence": 1.0,
            "badge": "attributed", "match_kind": None, "is_last_known": False,
            "prompt_excerpt": None, "prompt_hash": None, "edit_ratio": 0.0,
            "human_edit_lines": 0, "session_id": None, "event_id": None,
        }
    source = row["source"]
    model = row["model"]
    authored = row.get("content")
    current = "\n".join(lines[start - 1:end])
    edit_ratio = 0.0
    match_kind = row.get("match_kind")
    if authored is not None:
        # normalize both to "lines joined by \n, no trailing newline" so that
        # trailing-newline bookkeeping never registers as a human edit
        authored_norm = "\n".join(authored.splitlines())
        ratio = difflib.SequenceMatcher(None, authored_norm, current).ratio()
        edit_ratio = round(max(0.0, 1.0 - ratio), 4)
        match_kind = "carry" if edit_ratio <= 0.0001 else "edit"
    conf = conf_after_edit(base_confidence(source), edit_ratio)
    return {
        "start": start, "end": end, "source": source, "author": _author_label(source, model),
        "model": model, "confidence": conf, "badge": badge(conf), "match_kind": match_kind,
        "is_last_known": bool(match_kind == "edit"),
        "prompt_excerpt": row.get("prompt_excerpt"), "prompt_hash": row.get("prompt_hash"),
        "edit_ratio": edit_ratio,
        "human_edit_lines": (max(1, round(edit_ratio * (end - start + 1))) if edit_ratio > 0 else 0),
        "session_id": row.get("session_id"), "event_id": row["event_id"],
    }


def compute_blame(rows: list[dict], current_text: str, range_filter: tuple[int, int] | None = None) -> dict:
    lines = current_text.splitlines()
    n = len(lines)
    attrib: list[dict | None] = [None] * n
    for row in rows:  # ascending seq -> later events override earlier ones
        s, e = row["start_line"], min(row["end_line"], n)
        if s > n:
            continue
        for i in range(s - 1, e):
            if 0 <= i < n:
                attrib[i] = row

    spans: list[dict] = []
    i = 0
    while i < n:
        row = attrib[i]
        key = row["event_id"] if row else "__human__"
        j = i
        while j < n and ((attrib[j]["event_id"] if attrib[j] else "__human__") == key):
            j += 1
        spans.append(_span_from_row(i + 1, j, row, lines))
        i = j

    if range_filter:
        lo, hi = range_filter
        spans = [s for s in spans if not (s["end"] < lo or s["start"] > hi)]

    return {"lines": n, "spans": spans}


def summarize(spans: list[dict]) -> dict:
    """Authorship breakdown by source over the lines covered by `spans`."""
    by_source: dict[str, int] = {}
    models: set[str] = set()
    for s in spans:
        count = s["end"] - s["start"] + 1
        by_source[s["source"]] = by_source.get(s["source"], 0) + count
        if s.get("model"):
            models.add(s["model"])
    total = sum(by_source.values()) or 1
    pct = {k: round(100 * v / total, 1) for k, v in by_source.items()}
    return {"total_lines": sum(by_source.values()), "by_source": by_source, "pct": pct, "models": sorted(models)}
