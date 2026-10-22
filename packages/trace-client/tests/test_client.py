import json

from trace_client import TraceClient


def test_spools_when_no_daemon(tmp_path):
    c = TraceClient(home=tmp_path)
    ok = c.send_events([{"file_path": "a.py", "content": "x"}])
    assert ok is False  # no daemon.json -> cannot deliver
    files = list((tmp_path / "spool").glob("*.ndjson"))
    assert len(files) == 1
    rows = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert rows[0]["file_path"] == "a.py"


def test_empty_send_is_noop(tmp_path):
    c = TraceClient(home=tmp_path)
    assert c.send_events([]) is True
    assert not (tmp_path / "spool").exists()


def test_never_raises_on_garbage(tmp_path):
    c = TraceClient(home=tmp_path)
    # unserializable object in the payload must not crash the host process
    assert c.send_events([{"x": object()}]) is False
