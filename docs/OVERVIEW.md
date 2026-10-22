# What this repo is

`trace` is **git-native infrastructure for AI authorship provenance**. It records *which AI wrote which line of code, when, from what prompt, and how much a human changed it* — then surfaces that through a `git blame`-style CLI and a web dashboard. The commit author field only credits whoever pressed enter; `trace` recovers the truth underneath it (which model wrote the diff, from which prompt, and whether a human actually reviewed it).

This repository currently contains a **working M1 prototype + a dashboard**. The full vision is a 6-month plan in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## What works today

- **Capture** — a Claude Code hook records every file edit (which model, which prompt, which lines) and ships it to a local daemon.
- **`trace blame <file>`** — shows, per line, whether *you* or an *AI* wrote it, the prompt that produced it, a confidence badge, and a flag when a human hand-edited AI code.
- **`trace summary` / `trace status`** — repo-wide authorship breakdowns.
- **Dashboard** — a Next.js app that visualizes it all: AI %, per-file heatmaps, prompt→outcome by session, authorship over time.
- **Trust & privacy baked in** — prompts are encrypted at rest, provenance is tamper-evident (a BLAKE3 hash chain), and product telemetry is opt-in / off by default.

It runs entirely **locally** — no account, no cloud required.

---

## The repo at a glance

| Path | What it is | Status |
|---|---|---|
| [`packages/trace-core`](../packages/trace-core) | The shared standard: the `AuthorshipEvent` schema, canonical (RFC-8785) hashing, content addressing, the hash chain, the confidence model | ✅ built |
| [`packages/trace-daemon`](../packages/trace-daemon) | Local engine (Python/FastAPI): SQLite hot store, ingest, source classification, blame + human-edit detection, prompt encryption, the dashboard API | ✅ built |
| [`packages/trace-client`](../packages/trace-client) | Tiny SDK plugins use to send events without ever blocking the editor | ✅ built |
| [`packages/trace-capture-claude-code`](../packages/trace-capture-claude-code) | The Claude Code capture hook (the first editor integration) | ✅ built |
| [`packages/trace-cli`](../packages/trace-cli) | The `trace` command (`blame` / `summary` / `status` / `init` / `doctor`) | ✅ built |
| [`apps/dashboard`](../apps/dashboard) | The Next.js web dashboard | ✅ built |
| [`scripts/`](../scripts) | `e2e_smoke.py` (end-to-end demo) and `seed_demo.py` (sample data) | ✅ built |
| `git notes` + AST chunk tracker | Portable provenance in git + accuracy across refactors/commits | 🚧 M2 |
| cloud sync server · PR bot · more editors · compliance/SSO | Teams, GitHub reviews, Cursor/Copilot/Zed, enterprise | 🚧 M3–M6 |

---

## How it works (one idea + one pipeline)

**One idea:** separate the *immutable fact* from the *recomputable view*.
- An **`AuthorshipEvent`** is an immutable, content-addressed record: "claude-sonnet-4-5 wrote these 12 lines at time T, from prompt P." These never change.
- **Attribution** (which event owns a line *right now*) is a view recomputed as code moves and changes — so the algorithm can improve without ever rewriting history.

**One pipeline:**

```
Claude Code edit
   │  (hook)
   ▼
trace-client ──► trace daemon ──► SQLite hot store (+ BLAKE3 hash chain)
                  classify, blame        │
                                         ├──► trace blame / summary (CLI)
                                         └──► /api/* ──► Next.js dashboard
```

Everything flows one way and each layer is rebuildable from the one above it.

---

## Run it

```bash
uv sync --all-packages                       # set up the Python workspace
uv run python -m pytest packages -q          # 40 tests
uv run python scripts/e2e_smoke.py           # full capture → daemon → blame demo

# the dashboard, against sample data:
TRACE_HOME=/tmp/trace-demo uv run python scripts/seed_demo.py
TRACE_HOME=/tmp/trace-demo uv run trace-daemon            # terminal 1
cd apps/dashboard && TRACE_HOME=/tmp/trace-demo npm run dev   # terminal 2 → localhost:3000
```

---

## Learn more

- [README.md](../README.md) — the short pitch + quickstart
- [ARCHITECTURE.md](ARCHITECTURE.md) — the full architecture, data model, threat model, and 6-month roadmap
