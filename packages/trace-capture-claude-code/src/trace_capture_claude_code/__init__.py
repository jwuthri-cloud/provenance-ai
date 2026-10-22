"""trace — Claude Code capture (the first, reference capture integration).

Claude Code is chosen first precisely because it exposes a CLEAN authorship
signal: the PostToolUse tool-call. We capture file writes via hooks, correlate
the originating prompt + model via SessionStart/UserPromptSubmit + the session
transcript, and forward raw captures to the daemon (docs/ARCHITECTURE.md §7).
"""
from __future__ import annotations

__version__ = "0.1.0"
