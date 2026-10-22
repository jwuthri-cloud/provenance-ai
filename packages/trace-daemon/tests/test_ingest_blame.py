from trace_core import verify_chain
from trace_daemon.hotstore import HotStore
from trace_daemon.tracker import compute_blame, summarize
from trace_daemon.vault import Vault


def _store(tmp_path) -> HotStore:
    return HotStore(tmp_path / "db.sqlite", Vault(tmp_path / "vault.key"))


def _raw(**over) -> dict:
    base = dict(
        file_path="a.py",
        repo_id="git:test",
        raw_source_hint="claude_code_tool_call",
        model="claude-sonnet-4-5",
        session_id="s1",
        prompt_hash="sha256:p",
        prompt_excerpt="add function f",
        content="def f():\n    return 1\n",
        content_range={"start_line": 1, "end_line": 2},
        operation="create",
        timestamp="2026-05-31T00:00:00Z",
    )
    base.update(over)
    return base


def test_ingest_then_blame_attributes_ai(tmp_path):
    store = _store(tmp_path)
    res = store.ingest([_raw()])
    assert res["accepted"] == 1
    rows = store.query_file("git:test", "a.py")
    assert len(rows) == 1
    assert rows[0]["source"] == "claude_code_tool_call"
    assert rows[0]["prompt_excerpt"] == "add function f"  # decrypted from the vault

    blame = compute_blame(rows, "def f():\n    return 1\n")
    span = blame["spans"][0]
    assert span["source"] == "claude_code_tool_call"
    assert span["model"] == "claude-sonnet-4-5"
    assert span["badge"] == "attributed"
    assert span["edit_ratio"] == 0.0
    assert span["match_kind"] == "carry"
    store.close()


def test_prompt_encrypted_at_rest(tmp_path):
    store = _store(tmp_path)
    store.ingest([_raw()])
    raw_blob = store.conn.execute("SELECT prompt_excerpt_enc FROM events").fetchone()[0]
    assert raw_blob is not None
    assert b"add function f" not in raw_blob  # ciphertext, not plaintext
    store.close()


def test_human_edit_detected(tmp_path):
    store = _store(tmp_path)
    store.ingest([_raw()])
    rows = store.query_file("git:test", "a.py")
    blame = compute_blame(rows, "def f():\n    return 42  # tweaked by hand\n")
    span = blame["spans"][0]
    assert span["edit_ratio"] > 0
    assert span["match_kind"] == "edit"
    assert span["is_last_known"] is True
    assert span["confidence"] < 1.0
    store.close()


def test_idempotent_ingest(tmp_path):
    store = _store(tmp_path)
    assert store.ingest([_raw()])["accepted"] == 1
    assert store.ingest([_raw()])["accepted"] == 0  # same content-addressed id
    store.close()


def test_generated_path_classified(tmp_path):
    store = _store(tmp_path)
    store.ingest([_raw(file_path="package-lock.json", content="{}\n",
                       content_range={"start_line": 1, "end_line": 1})])
    rows = store.query_file("git:test", "package-lock.json")
    assert rows[0]["source"] == "generated"
    store.close()


def test_human_lines_are_baseline(tmp_path):
    store = _store(tmp_path)
    store.ingest([_raw(content="def f():\n    return 1\n", content_range={"start_line": 2, "end_line": 3})])
    rows = store.query_file("git:test", "a.py")
    # line 1 has no event -> attributed to the human baseline
    blame = compute_blame(rows, "import os\ndef f():\n    return 1\n")
    first = blame["spans"][0]
    assert first["start"] == 1 and first["source"] == "human_keyboard"
    assert first["author"] == "you (keyboard)"
    store.close()


def test_chain_intact_after_ingest(tmp_path):
    store = _store(tmp_path)
    store.ingest([
        _raw(content="a\n", content_range={"start_line": 1, "end_line": 1}),
        _raw(content="b\n", content_range={"start_line": 2, "end_line": 2}),
    ])
    rows = store.conn.execute(
        "SELECT prev_hash, event_id, content_hash, chain_hash FROM events ORDER BY seq"
    ).fetchall()
    seq = [(r["prev_hash"], r["event_id"], r["content_hash"], r["chain_hash"]) for r in rows]
    assert len(seq) == 2
    assert verify_chain(seq) is None
    store.close()


def test_summary_breakdown(tmp_path):
    store = _store(tmp_path)
    store.ingest([_raw(content_range={"start_line": 1, "end_line": 2})])
    rows = store.query_file("git:test", "a.py")
    blame = compute_blame(rows, "def f():\n    return 1\nx = 9\n")  # 3rd line is human
    s = summarize(blame["spans"])
    assert s["by_source"]["claude_code_tool_call"] == 2
    assert s["by_source"]["human_keyboard"] == 1
    store.close()
