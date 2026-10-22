"""Canonical, byte-stable serialization for content addressing.

`event_id` and `content_hash` MUST be byte-identical across independent machines
and implementations, or git-notes portability, cross-tier dedup, and the
conformance suite all silently break. We lock RFC 8785 (JSON Canonicalization
Scheme) as the one canonical serialization. See docs/ARCHITECTURE.md §3.

A pure-stdlib fallback is provided so the package still functions if the optional
`rfc8785` wheel is unavailable; the fallback produces the same bytes for the
JSON value subset we use (objects, arrays, strings, integers, null).
"""
from __future__ import annotations

from typing import Any

try:  # preferred: the spec-grade implementation
    import rfc8785 as _rfc8785

    def canonical_bytes(obj: Any) -> bytes:
        """Return the RFC 8785 canonical UTF-8 bytes for a JSON-compatible value."""
        return _rfc8785.dumps(obj)

    CANONICALIZER = "rfc8785"
except Exception:  # pragma: no cover - exercised only when the wheel is missing
    import json

    def canonical_bytes(obj: Any) -> bytes:
        """Stdlib fallback canonicalization (sorted keys, compact, UTF-8)."""
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    CANONICALIZER = "stdlib-fallback"
