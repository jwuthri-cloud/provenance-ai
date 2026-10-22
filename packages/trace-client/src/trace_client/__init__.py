"""trace-client — the thin capture SDK.

Kept stdlib-only and tiny because it is imported inside editor/hook processes.
Its whole job: get events to the daemon WITHOUT ever blocking or crashing the
host process. Network failure -> spool to disk; repeated failure -> open a
circuit breaker and spool directly (docs/ARCHITECTURE.md §7, latency budget).
"""
from __future__ import annotations

from .client import TraceClient, trace_home

__all__ = ["TraceClient", "trace_home"]
__version__ = "0.1.0"
