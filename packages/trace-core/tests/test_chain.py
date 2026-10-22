from trace_core import chain_hash, verify_chain


def test_links_deterministic_and_distinct():
    h1 = chain_hash(None, "evt_a", "blake3:1")
    h2 = chain_hash(h1, "evt_b", "blake3:2")
    assert len(h1) == 64 and h1 != h2
    assert chain_hash(None, "evt_a", "blake3:1") == h1  # deterministic


def test_tamper_changes_link():
    h1 = chain_hash(None, "evt_a", "blake3:1")
    good = chain_hash(h1, "evt_b", "blake3:2")
    tampered = chain_hash(h1, "evt_b", "blake3:TAMPERED")
    assert good != tampered


def test_verify_chain_detects_break():
    h1 = chain_hash(None, "evt_a", "blake3:1")
    h2 = chain_hash(h1, "evt_b", "blake3:2")
    intact = [(None, "evt_a", "blake3:1", h1), (h1, "evt_b", "blake3:2", h2)]
    assert verify_chain(intact) is None

    # tamper the second event's stored content hash without re-deriving its link
    broken = [(None, "evt_a", "blake3:1", h1), (h1, "evt_b", "blake3:EVIL", h2)]
    assert verify_chain(broken) == 1
