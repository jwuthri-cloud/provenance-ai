from trace_core import canonical_bytes


def test_sorted_and_compact():
    assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_key_order_invariant():
    assert canonical_bytes({"a": 1, "b": {"x": 1, "y": 2}}) == canonical_bytes(
        {"b": {"y": 2, "x": 1}, "a": 1}
    )


def test_unicode_preserved_utf8():
    out = canonical_bytes({"k": "café"})
    assert "café".encode("utf-8") in out


def test_null_and_nested():
    assert canonical_bytes({"z": None, "a": [3, 2, 1]}) == b'{"a":[3,2,1],"z":null}'
