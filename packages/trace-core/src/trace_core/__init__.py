"""trace-core — the shared foundation and CC0 standard surface.

Immutable, content-addressed AuthorshipEvents + canonical hashing + hash chain +
the one confidence contract. Imported by the daemon, CLI, capture plugins, and
(conceptually) the cloud server. See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from .canonical import CANONICALIZER, canonical_bytes
from .chain import GENESIS, chain_hash, verify_chain
from .confidence import (
    APPROXIMATE,
    ATTRIBUTED,
    UNATTRIBUTED,
    badge,
    base_confidence,
    conf_after_edit,
)
from .hashing import compute_event_id, content_hash, hash_hex
from .models import (
    SCHEMA_VERSION,
    AuthorshipEvent,
    ContentRange,
    HumanModifications,
    MatchKind,
    Operation,
    Source,
)

__all__ = [
    "SCHEMA_VERSION",
    "AuthorshipEvent",
    "ContentRange",
    "HumanModifications",
    "MatchKind",
    "Operation",
    "Source",
    "canonical_bytes",
    "CANONICALIZER",
    "compute_event_id",
    "content_hash",
    "hash_hex",
    "chain_hash",
    "verify_chain",
    "GENESIS",
    "base_confidence",
    "conf_after_edit",
    "badge",
    "ATTRIBUTED",
    "APPROXIMATE",
    "UNATTRIBUTED",
]

__version__ = "0.1.0"
