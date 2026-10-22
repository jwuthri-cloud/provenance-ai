"""Fire-and-forget event sender with on-disk spool + file-based circuit breaker.

Design contract (docs/ARCHITECTURE.md):
  * Never raise into the host process. Every public call is best-effort.
  * Try the daemon over loopback HTTP with a short timeout and the per-daemon
    token. On any failure, append the events to a spool file the daemon drains
    later, so capture is never lost even if the daemon is down.
  * A file-based circuit breaker avoids hammering a dead daemon from many
    short-lived hook processes.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BREAKER_THRESHOLD = 3       # consecutive failures before opening
BREAKER_COOLDOWN_S = 30.0   # how long the breaker stays open
DEFAULT_TIMEOUT_S = 0.5     # never make the editor/hook wait long


def trace_home() -> Path:
    """Resolve the trace state directory (shared with the daemon)."""
    return Path(os.environ.get("TRACE_HOME", str(Path.home() / ".trace")))


class TraceClient:
    def __init__(
        self,
        home: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.home = home or trace_home()
        self.timeout = timeout
        self.spool_dir = self.home / "spool"
        self.breaker_path = self.home / "breaker.json"

    # ---- public API ---------------------------------------------------------
    def send_events(self, events: list[dict]) -> bool:
        """Best-effort delivery. Returns True if the daemon acked, else spools.

        Never raises.
        """
        if not events:
            return True
        try:
            if self._breaker_open():
                self._spool(events)
                return False
            info = self._daemon_info()
            if not info:
                self._spool(events)
                return False
            ok = self._post(info, events)
            if ok:
                self._breaker_reset()
                return True
            self._breaker_record_failure()
            self._spool(events)
            return False
        except Exception:
            # absolute backstop — capture must never break the host process
            try:
                self._spool(events)
            except Exception:
                pass
            return False

    # ---- internals ----------------------------------------------------------
    def _daemon_info(self) -> dict | None:
        try:
            return json.loads((self.home / "daemon.json").read_text())
        except Exception:
            return None

    def _post(self, info: dict, events: list[dict]) -> bool:
        body = ("\n".join(json.dumps(e) for e in events)).encode("utf-8")
        url = f"http://{info.get('host', '127.0.0.1')}:{info['port']}/ingest"
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-ndjson",
                "X-Trace-Token": info.get("token", ""),
                "Host": "127.0.0.1",  # strict host; defeats DNS-rebinding on the loopback surface
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _spool(self, events: list[dict]) -> None:
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        # unique-ish filename without Math.random/time collisions across procs
        name = f"{int(time.time() * 1000)}-{os.getpid()}.ndjson"
        path = self.spool_dir / name
        with path.open("a", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")

    # ---- circuit breaker (file-based, survives across short-lived procs) -----
    def _breaker_state(self) -> dict:
        try:
            return json.loads(self.breaker_path.read_text())
        except Exception:
            return {"fail_count": 0, "open_until": 0.0}

    def _breaker_open(self) -> bool:
        return self._breaker_state().get("open_until", 0.0) > time.time()

    def _breaker_record_failure(self) -> None:
        st = self._breaker_state()
        st["fail_count"] = st.get("fail_count", 0) + 1
        if st["fail_count"] >= BREAKER_THRESHOLD:
            st["open_until"] = time.time() + BREAKER_COOLDOWN_S
        self._write_breaker(st)

    def _breaker_reset(self) -> None:
        self._write_breaker({"fail_count": 0, "open_until": 0.0})

    def _write_breaker(self, st: dict) -> None:
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            self.breaker_path.write_text(json.dumps(st))
        except Exception:
            pass
