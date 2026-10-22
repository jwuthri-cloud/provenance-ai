"""Spool drainer — durability backstop when the daemon was down at capture time.

Plugins spool events to TRACE_HOME/spool/*.ndjson when they can't reach the
daemon. The daemon drains them on startup and periodically, so capture is never
lost (docs/ARCHITECTURE.md §7).
"""
from __future__ import annotations

import json
import threading

from . import config
from .hotstore import HotStore


def drain_once(store: HotStore) -> int:
    d = config.spool_dir()
    if not d.exists():
        return 0
    total = 0
    for f in sorted(d.glob("*.ndjson")):
        try:
            raws = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        except Exception:
            continue
        try:
            res = store.ingest(raws)
            total += res["accepted"]
            f.unlink()
        except Exception:
            # leave the file for a later attempt
            continue
    return total


class SpoolDrainer(threading.Thread):
    def __init__(self, store: HotStore, interval: float = 5.0) -> None:
        super().__init__(daemon=True)
        self.store = store
        self.interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                drain_once(self.store)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
