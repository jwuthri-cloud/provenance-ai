#!/usr/bin/env python3
"""End-to-end smoke test for the trace M1 vertical slice.

Exercises the REAL wiring, not mocks:
    trace-claude-hook (stdin JSON)  ->  trace-client  ->  trace-daemon (HTTP)
    ->  SQLite hot store  ->  trace blame

Runs hermetically against a temp TRACE_HOME so it never touches your real
~/.trace. Usage:  uv run python scripts/e2e_smoke.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
PORT = "47137"


def hr(title: str) -> None:
    print(f"\n\033[1;36m=== {title} ===\033[0m")


def run_hook(env: dict, payload: dict) -> None:
    subprocess.run(
        [PY, "-m", "trace_capture_claude_code.hook"],
        input=json.dumps(payload),
        text=True,
        env=env,
        cwd=str(REPO),
        check=False,
    )


def trace(env: dict, *args: str) -> None:
    subprocess.run([PY, "-m", "trace_cli.app", *args], env=env, cwd=str(REPO), check=False)


def wait_health(port: str, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # interleave cleanly with subprocess output
    home = Path(tempfile.mkdtemp(prefix="trace-e2e-"))
    env = {**os.environ, "TRACE_HOME": str(home), "TRACE_PORT": PORT, "TRACE_TELEMETRY": "1"}
    demo = REPO / "demo" / "sample.py"
    demo.parent.mkdir(parents=True, exist_ok=True)
    transcript = home / "transcript.jsonl"
    transcript.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-4-5"}}) + "\n")

    daemon = subprocess.Popen([PY, "-m", "trace_daemon"], env=env)
    try:
        hr("1. daemon boot")
        if not wait_health(PORT):
            print("daemon did not become healthy")
            return 1
        print(f"daemon healthy on :{PORT}  (TRACE_HOME={home})")

        hr("2. simulate a Claude Code session writing code")
        sid = "sess_demo"
        run_hook(env, {"hook_event_name": "SessionStart", "session_id": sid,
                       "cwd": str(REPO), "transcript_path": str(transcript)})
        run_hook(env, {"hook_event_name": "UserPromptSubmit", "session_id": sid,
                       "prompt": "add a rate limiter to the login endpoint"})

        ai_code = (
            "import time\n"
            "\n"
            "def rate_limit(key, limit=5, window=60):\n"
            "    now = time.time()\n"
            "    bucket = _buckets.setdefault(key, [])\n"
            "    bucket[:] = [t for t in bucket if now - t < window]\n"
            "    if len(bucket) >= limit:\n"
            "        return False\n"
            "    bucket.append(now)\n"
            "    return True\n"
        )
        demo.write_text(ai_code)  # the file exists with AI content before PostToolUse fires
        run_hook(env, {"hook_event_name": "PostToolUse", "session_id": sid,
                       "tool_name": "Write", "tool_input": {"file_path": str(demo), "content": ai_code},
                       "transcript_path": str(transcript), "cwd": str(REPO)})
        print("captured: SessionStart, UserPromptSubmit, PostToolUse(Write)")

        hr("3. trace blame demo/sample.py  (fresh AI authorship)")
        trace(env, "blame", "demo/sample.py", "--show-prompts")

        hr("4. a human hand-edits two lines, then re-blame")
        edited = ai_code.replace("limit=5", "limit=10").replace("return False", "raise TooMany()  # human")
        demo.write_text(edited)
        trace(env, "blame", "demo/sample.py")

        hr("5. trace status")
        trace(env, "status")

        hr("6. trace summary")
        trace(env, "summary")

        hr("7. product telemetry (opt-in, local-only, counts only)")
        tpath = home / "telemetry.jsonl"
        if tpath.exists():
            for line in tpath.read_text().splitlines():
                print("  " + line)
        return 0
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except Exception:
            daemon.kill()
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(REPO / "demo", ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
