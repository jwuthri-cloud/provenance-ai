"""Per-event BLAKE3 hash chain — tamper-evidence built into the write path (M1).

Each stored event carries a `prev_hash` linking it to the previous event in the
local chain. A verifier (M2 `trace verify`) recomputes the chain; any silent
edit, reorder, or strip of an event breaks continuity. Cheap to add now, brutal
to retrofit later (docs/ARCHITECTURE.md §7).
"""
from __future__ import annotations

from .hashing import hash_hex

GENESIS = "GENESIS"


def chain_hash(prev_hash: str | None, event_id: str, content_hash: str) -> str:
    """Compute the chain link for an event given the previous link.

    Deterministic and order-sensitive: changing any input (including the prior
    link) changes the output, so the chain detects tampering and reordering.
    """
    base = f"{prev_hash or GENESIS}|{event_id}|{content_hash}".encode("utf-8")
    return hash_hex(base)


def verify_chain(events: list[tuple[str | None, str, str, str]]) -> int | None:
    """Verify a sequence of (prev_hash, event_id, content_hash, stored_chain_hash).

    Returns the index of the first broken link, or None if the whole chain is
    intact. The recomputed prev for link N must equal the stored chain hash of
    link N-1.
    """
    expected_prev: str | None = None
    for i, (prev_hash, event_id, content_hash, stored) in enumerate(events):
        if prev_hash != expected_prev:
            return i
        recomputed = chain_hash(prev_hash, event_id, content_hash)
        if recomputed != stored:
            return i
        expected_prev = stored
    return None
