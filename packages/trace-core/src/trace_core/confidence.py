"""The single confidence contract (docs/ARCHITECTURE.md §3, cross-cutting decision).

`attribution confidence` (this module) is distinct from `classifier_confidence`
(how sure we are of the *source*) and from cryptographic `verification_status`.
Every surface renders the SAME three-state badge off the SAME number.
"""
from __future__ import annotations

# source value -> base attribution confidence.
# Declared agent tool-calls and known-human keystrokes are authoritative (1.0);
# completions are strong; pastes are weaker; `inferred` is a floor.
BASE_CONFIDENCE: dict[str, float] = {
    "claude_code_tool_call": 1.0,
    "cursor_agent": 1.0,
    "copilot_agent": 1.0,
    "zed_agent": 1.0,
    "human_keyboard": 1.0,
    "generated": 1.0,  # high confidence it is *generated* (neither AI nor human authored)
    "cursor_autocomplete": 0.9,
    "copilot_completion": 0.9,
    "ai_paste": 0.7,
    "human_paste": 0.6,
    "inferred": 0.4,
}

ATTRIBUTED = "attributed"
APPROXIMATE = "approximate"  # low-confidence / last-known
UNATTRIBUTED = "unattributed"


def base_confidence(source) -> float:
    """Base confidence for a Source (enum or str)."""
    s = source.value if hasattr(source, "value") else str(source)
    return BASE_CONFIDENCE.get(s, 0.5)


def conf_after_edit(base: float, edit_ratio: float) -> float:
    """Monotonic non-increasing decay as a human edits authored content.

    edit_ratio in [0,1]; 0 -> unchanged, 1 -> fully rewritten. A subsequent
    *declared* re-authoring resets to base elsewhere (handled by the tracker).
    """
    edit_ratio = max(0.0, min(1.0, edit_ratio))
    return round(base * (1.0 - edit_ratio), 4)


def badge(confidence: float) -> str:
    """Three-state rendering shared by CLI, PR bot, and dashboard."""
    if confidence >= 0.8:
        return ATTRIBUTED
    if confidence >= 0.4:
        return APPROXIMATE
    return UNATTRIBUTED
