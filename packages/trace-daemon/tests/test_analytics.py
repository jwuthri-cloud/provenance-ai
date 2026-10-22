from trace_daemon.hotstore import HotStore
from trace_daemon.vault import Vault


def _store(tmp_path) -> HotStore:
    return HotStore(tmp_path / "db.sqlite", Vault(tmp_path / "vault.key"))


def _raw(**over) -> dict:
    base = dict(
        file_path="src/a.py", repo_id="git:test", raw_source_hint="claude_code_tool_call",
        model="claude-sonnet-4-5", session_id="s1", prompt_excerpt="add f",
        content="x = 1\n", content_range={"start_line": 1, "end_line": 1},
        operation="insert", timestamp="2026-06-01T00:00:00Z",
    )
    base.update(over)
    return base


def test_overview_splits_ai_human_generated(tmp_path):
    store = _store(tmp_path)
    store.ingest([
        _raw(content="a\nb\nc\n", content_range={"start_line": 1, "end_line": 3}),
        _raw(raw_source_hint="human_keyboard", model=None, session_id=None,
             content="h\n", content_range={"start_line": 4, "end_line": 4}),
        _raw(file_path="package-lock.json", content="{}\n",
             content_range={"start_line": 1, "end_line": 1}),
    ])
    ov = store.overview()
    assert ov["ai_lines"] == 3
    assert ov["human_lines"] == 1
    assert ov["generated_lines"] == 1
    assert ov["total_lines"] == 5
    assert ov["ai_pct"] == 60.0
    assert len(ov["recent"]) == 3
    store.close()


def test_files_aggregate_and_flag(tmp_path):
    store = _store(tmp_path)
    store.ingest([_raw(content="a\nb\nc\nd\n", content_range={"start_line": 1, "end_line": 4})])
    files = store.files()
    assert len(files) == 1
    f = files[0]
    assert f["file"] == "src/a.py"
    assert f["ai_pct"] == 100.0
    assert f["flagged"] is True
    assert f["top_model"] == "claude-sonnet-4-5"
    store.close()


def test_sessions_and_timeline(tmp_path):
    store = _store(tmp_path)
    store.ingest([
        _raw(session_id="s1", timestamp="2026-06-01T09:00:00Z"),
        _raw(session_id="s2", model="claude-opus-4-8", file_path="src/b.py",
             timestamp="2026-06-02T09:00:00Z", content="y = 2\n",
             content_range={"start_line": 1, "end_line": 1}),
    ])
    sessions = {s["session_id"]: s for s in store.sessions()}
    assert sessions["s1"]["prompt_excerpt"] == "add f"
    assert sessions["s2"]["model"] == "claude-opus-4-8"

    timeline = store.timeline()
    days = {t["day"] for t in timeline}
    assert days == {"2026-06-01", "2026-06-02"}
    store.close()
