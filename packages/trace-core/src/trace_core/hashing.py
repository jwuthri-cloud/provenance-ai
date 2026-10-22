"""Content-addressed hashing primitives (BLAKE3 over canonical bytes)."""
from __future__ import annotations

from blake3 import blake3

from .canonical import canonical_bytes

EVENT_ID_PREFIX = "evt_"
EVENT_ID_HEX_LEN = 32  # 128 bits of the digest — ample collision resistance


def hash_hex(data: bytes) -> str:
    """Lowercase hex BLAKE3 digest of raw bytes."""
    return blake3(data).hexdigest()


def content_hash(text: str) -> str:
    """Content hash of authored text, namespaced so the algorithm is self-describing."""
    return "blake3:" + blake3(text.encode("utf-8")).hexdigest()


def compute_event_id(identity_core: dict) -> str:
    """Deterministic, content-addressed event id from the event's identity fields.

    Identical identity input -> identical id on any machine (this is the
    cross-clone portability guarantee). Volatile/derived fields (received_at,
    prev_hash, confidence, prompt_excerpt, human_modifications_after) are
    excluded from identity by construction in `AuthorshipEvent.identity_core`.
    """
    return EVENT_ID_PREFIX + hash_hex(canonical_bytes(identity_core))[:EVENT_ID_HEX_LEN]
