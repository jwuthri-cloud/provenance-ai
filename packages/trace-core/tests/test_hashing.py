import json

from trace_core import AuthorshipEvent, Operation, Source, canonical_bytes, content_hash


def make(**over) -> AuthorshipEvent:
    base = dict(
        timestamp="2026-05-31T14:22:01Z",
        source=Source.claude_code_tool_call,
        file_path="src/auth.py",
        content="def f():\n    return 1\n",
        content_range={"start_line": 42, "end_line": 58},
        operation=Operation.insert,
        model="claude-sonnet-4-5",
        session_id="sess_8f2a",
        prompt_hash="sha256:abc",
        git_branch="feature/x",
        repo_id="repo_123",
        user_id="local:laurent",
    )
    base.update(over)
    return AuthorshipEvent.create(**base)


def test_event_id_is_deterministic_and_prefixed():
    a, b = make(), make()
    assert a.event_id == b.event_id
    assert a.event_id.startswith("evt_")


def test_canonical_bytes_invariant_to_dict_order():
    assert canonical_bytes({"a": 1, "b": 2}) == canonical_bytes({"b": 2, "a": 1})


def test_content_hash_namespaced_and_sensitive():
    assert content_hash("hello").startswith("blake3:")
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("hello\n")


def test_different_content_changes_event_id():
    assert make().event_id != make(content="def f():\n    return 2\n").event_id


def test_cross_machine_determinism_via_json_roundtrip():
    """Simulate a second machine: serialize the identity inputs to JSON and back
    (keys reordered, enums as strings), rebuild the event, and require the same id.
    This is the cross-clone portability guarantee."""
    a = make()
    wire = json.loads(
        json.dumps(
            {
                "content_range": {"end_line": 58, "start_line": 42},  # reordered
                "user_id": a.user_id,
                "repo_id": a.repo_id,
                "git_branch": a.git_branch,
                "operation": a.operation.value,
                "content_hash": a.content_hash,
                "prompt_hash": a.prompt_hash,
                "session_id": a.session_id,
                "model": a.model,
                "file_path": a.file_path,
                "source": a.source.value,
                "timestamp": a.timestamp,
            }
        )
    )
    b = AuthorshipEvent.create(
        timestamp=wire["timestamp"],
        source=Source(wire["source"]),
        file_path=wire["file_path"],
        content_hash=wire["content_hash"],
        content_range=wire["content_range"],
        operation=Operation(wire["operation"]),
        model=wire["model"],
        session_id=wire["session_id"],
        prompt_hash=wire["prompt_hash"],
        git_branch=wire["git_branch"],
        repo_id=wire["repo_id"],
        user_id=wire["user_id"],
    )
    assert a.event_id == b.event_id
