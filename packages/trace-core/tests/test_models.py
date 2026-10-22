import pytest

from trace_core import AuthorshipEvent, ContentRange, MatchKind, Operation, Source


def _ev(**over) -> AuthorshipEvent:
    base = dict(
        timestamp="2026-05-31T00:00:00Z",
        source=Source.claude_code_tool_call,
        file_path="a.py",
        content="x = 1\n",
        content_range={"start_line": 1, "end_line": 1},
        operation=Operation.insert,
    )
    base.update(over)
    return AuthorshipEvent.create(**base)


def test_create_minimal():
    e = _ev()
    assert e.content_hash.startswith("blake3:")
    assert e.event_id.startswith("evt_")
    assert e.schema_version == 1


def test_create_requires_content_or_hash():
    with pytest.raises(ValueError):
        AuthorshipEvent.create(
            timestamp="t",
            source=Source.human_keyboard,
            file_path="a.py",
            content_range={"start_line": 1, "end_line": 1},
            operation=Operation.insert,
        )


def test_content_range_rejects_inverted():
    with pytest.raises(Exception):
        ContentRange(start_line=5, end_line=2)
    with pytest.raises(Exception):
        ContentRange(start_line=0, end_line=1)


def test_json_roundtrip_preserves_identity():
    e = _ev(match_kind=MatchKind.carry)
    dumped = e.model_dump(mode="json")
    restored = AuthorshipEvent(**dumped)
    assert restored.event_id == e.event_id
    assert restored.source == Source.claude_code_tool_call
    assert restored.match_kind == MatchKind.carry


def test_string_enums_accepted():
    e = _ev(source="human_keyboard", operation="replace")
    assert e.source == Source.human_keyboard
    assert e.operation == Operation.replace
