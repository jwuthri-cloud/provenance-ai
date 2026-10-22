from trace_capture_claude_code.hook import _captures_for_edit, _line_count, _locate_span
from trace_capture_claude_code.session import redact


def test_locate_span_multiline():
    text = "line1\nline2\ntarget_a\ntarget_b\nlast\n"
    assert _locate_span(text, "target_a\ntarget_b") == (3, 4)
    assert _locate_span(text, "line1") == (1, 1)
    assert _locate_span(text, "nope") is None


def test_line_count():
    assert _line_count("a\nb\nc\n") == 3
    assert _line_count("single") == 1


def test_write_capture_is_whole_file():
    base = {"abs_path": "/x/a.py", "raw_source_hint": "claude_code_tool_call"}
    caps = _captures_for_edit("Write", {"content": "a\nb\nc\n"}, "", base)
    assert len(caps) == 1
    assert caps[0]["content_range"] == {"start_line": 1, "end_line": 3}
    assert caps[0]["operation"] == "create"
    assert caps[0]["raw_source_hint"] == "claude_code_tool_call"


def test_edit_capture_locates_span():
    file_text = "header\n\ndef g():\n    return 2\n"
    base = {"abs_path": "/x/a.py", "raw_source_hint": "claude_code_tool_call"}
    caps = _captures_for_edit(
        "Edit",
        {"old_string": "return 1", "new_string": "def g():\n    return 2"},
        file_text,
        base,
    )
    assert caps[0]["content_range"]["start_line"] == 3
    assert caps[0]["content_range"]["end_line"] == 4
    assert caps[0]["operation"] == "replace"


def test_multiedit_yields_one_capture_per_edit():
    file_text = "alpha\nbeta\ngamma\n"
    base = {"abs_path": "/x/a.py", "raw_source_hint": "claude_code_tool_call"}
    caps = _captures_for_edit(
        "MultiEdit",
        {"edits": [{"old_string": "alpha", "new_string": "alpha"},
                   {"old_string": "gamma", "new_string": "gamma"}]},
        file_text,
        base,
    )
    assert len(caps) == 2


def test_redaction_masks_secrets():
    out = redact("here is sk-ABCDEFGHIJKLMNOahsdkjfh and a token")
    assert "sk-ABCDEFGHIJKLMNO" not in out
    assert "[REDACTED]" in out
