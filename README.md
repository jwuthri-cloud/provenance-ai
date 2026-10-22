# `trace` *(working name)*

**Git for AI authorship. Know who — and what — wrote every line.**

`trace` is git-native infrastructure for tracking AI authorship in code. It captures *which AI wrote which line, when, with what prompt, and how much a human modified it* — then surfaces that through a `git blame`-style CLI, a GitHub PR comment bot, and a queryable dashboard. Provenance is stored durably and portably (it survives clone, push, pull, and fork) via local SQLite + git notes, with an optional cloud tier.

Today the commit author field credits the human who pressed enter, not the model that generated the diff. As AI authorship grows, that gap becomes a problem for code review, debugging, security audits, and compliance. `trace` closes it — and aims to become the **open, neutral, git-aligned standard** for AI provenance (the `.gitignore` of AI authorship).

## Status

The founding architecture and 6-month roadmap live in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

**M1 (the foundation) is built and working**: the `trace-core` standard surface, a Python/FastAPI daemon (SQLite WAL hot store, classification, blame, hash chain, prompt encryption at rest), the Claude Code capture hook, and the `trace` CLI. `trace blame` already attributes Claude-Code-authored vs human-typed lines — and flags human edits to AI code — in a live session.

## Try it (M1)

```bash
uv sync --all-packages                     # set up the workspace venv
uv run python -m pytest packages -q        # 37 tests
uv run python scripts/e2e_smoke.py         # full capture -> daemon -> blame demo (hermetic)
```

To use it for real in this repo:

```bash
uv run trace init                          # wire Claude Code hooks (project-local) + token/key
uv run trace daemon                        # run the daemon (separate terminal)
# ...let Claude Code edit files...
uv run trace blame <file> --show-prompts   # see who/what wrote each line
uv run trace status        # event counts, models, chain head
uv run trace summary       # repo-wide authorship breakdown
```

State lives under `~/.trace` (override with `TRACE_HOME`); product telemetry is **off** unless you set `TRACE_TELEMETRY=1`.

## Stack

- **Daemon + backend:** Python + FastAPI
- **Frontend / dashboard:** Next.js (App Router)
- **First capture integration:** Claude Code (hooks + session transcript)
- **Storage:** local SQLite (hot) → git notes (`refs/notes/trace`, portable) → optional cold server
- **Format:** CC0 open standard; implementation Apache-2.0

## The one idea to understand first

Separate the **immutable fact** (an append-only, content-addressed `AuthorshipEvent`) from the **recomputable view** (`ChunkAttribution`, re-derived every commit by a `git blame -C -M`-style chunk tracker). Attribution becomes a pure function of *(events, current tree)*, so the algorithm can improve without ever rewriting history. Everything else follows from that. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
