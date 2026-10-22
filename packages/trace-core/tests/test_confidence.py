from trace_core import APPROXIMATE, ATTRIBUTED, UNATTRIBUTED, Source, badge, base_confidence, conf_after_edit


def test_base_confidence_by_source():
    assert base_confidence(Source.claude_code_tool_call) == 1.0
    assert base_confidence(Source.human_keyboard) == 1.0
    assert base_confidence(Source.cursor_autocomplete) == 0.9
    assert base_confidence(Source.inferred) == 0.4
    assert base_confidence("totally_unknown_source") == 0.5


def test_decay_is_monotonic_non_increasing():
    b = base_confidence(Source.claude_code_tool_call)
    assert conf_after_edit(b, 0.0) == 1.0
    assert conf_after_edit(b, 1.0) == 0.0
    assert conf_after_edit(b, 0.3) >= conf_after_edit(b, 0.6)


def test_badge_thresholds():
    assert badge(0.95) == ATTRIBUTED
    assert badge(0.8) == ATTRIBUTED
    assert badge(0.5) == APPROXIMATE
    assert badge(0.39) == UNATTRIBUTED
