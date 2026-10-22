"""trace-cli — the primary v1 surface.

For M1 the CLI reads the hot store directly (SQLite WAL allows concurrent readers
while the daemon writes), so `blame`/`summary`/`status` work even when the daemon
process is not running. The daemon is required only for live ingest.
"""
from __future__ import annotations

__version__ = "0.1.0"
