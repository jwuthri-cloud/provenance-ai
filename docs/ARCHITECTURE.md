# `trace` — Architecture & 6-Month Roadmap

> Working name; final TBD. **"Git for AI authorship. Know who — and what — wrote every line."**
> Status: founding architecture (whole-roadmap). Greenfield repo.

---

## 0. Context — why this document exists

AI now writes a meaningful share of production code, but git's author field credits the human who pressed enter, not the model that generated the diff. The prompt that produced the code, the model version, and how much a human actually reviewed/edited it are all lost the moment a session ends. That gap hurts code review (a 2,000-line agent PR gets the same scrutiny as a 50-line human one), debugging (no prompt to replay), security audits (can't tell human-vetted from auto-generated), and compliance (SOC 2 / EU AI Act increasingly want records of AI involvement).

`trace` closes the gap: it captures *which AI wrote which line, when, with what prompt, and how much a human modified it*, then surfaces that through a `git blame`-style CLI, a GitHub PR bot, and a dashboard — stored durably and portably alongside git history. The north-star is to become **the open, neutral, git-aligned standard for AI provenance** (the `.gitignore` of AI authorship).

**Scope of this document.** A whole-roadmap *architecture* across the PRD's 6 months — the load-bearing decisions, component map, contracts, and sequencing — not line-by-line code. It is the blueprint M1 builds against.

**Locked stack decisions** (these override the PRD where they conflict):

| Decision | Choice | Note |
|---|---|---|
| Local daemon + cloud backend | **Python + FastAPI** | Prototype-first. A native (Rust/Go) hot path replaces only the latency-critical inner loop later, behind a published byte-protocol seam — *if* a benchmark gate demands it. |
| Frontend / dashboard | **Next.js** (App Router) | |
| First capture integration | **Claude Code** (hooks + transcript JSONL) | Cursor, VS Code + Copilot, Zed are later phases. Claude Code is chosen first precisely because it exposes a *clean* authorship signal (the `PostToolUse` tool-call). |

*This document was produced by a multi-agent design pass (9 domain architects → synthesis → adversarial completeness critique). Where the critique found gaps, the fixes are folded into the roadmap below and marked `[review-fix]`.*

---

## 1. The architectural spine

One decision underpins everything: **separate the immutable fact from the recomputable view.**

- **`AuthorshipEvent`** — an immutable, content-addressed, append-only fact ("claude-sonnet-4-5 wrote these 12 normalized lines at T, from prompt P, in session S"). This is the unit we publish as the open standard.
- **`ChunkAttribution`** — a *mutable materialized view* (`chunk_uid → winning event + confidence + edit_ratio`) recomputed on every commit by the `ChunkTracker`.

Why it matters: provenance facts are immutable history, but *where* a chunk currently lives drifts every commit as code is edited, moved, split, and reformatted. Conflating the two would force destructive rewrites of history on every refactor. The split makes attribution **a pure, re-runnable function of `(events, current tree)`** — a tracker bugfix re-derives correct blame from the same event log with zero data loss, and the published format stays frozen while the algorithm iterates aggressively behind it.

Corollary — **one-way materialization, every tier rebuildable from the one upstream of it:**

```
SQLite hot store (durable source of truth, last 30 days)
        │  emitted at commit
        ▼
git notes  refs/notes/trace  (portable per-commit projection)
        │  opt-in sync (events, not refs)
        ▼
optional cold FastAPI server (full history, dashboards)
   + .trace/manifest.json sidecar (onboarding)
```

Crash-safety comes from ack-after-durable-write to a fast local store, **not** synchronous git-ref mutation per event. A lost or rewritten note is always recoverable from the tier above it.

---

## 2. End-to-end shape

```
┌──────────────── CAPTURE (thin signal-scavengers) ─────────────────┐
│  Claude Code hooks (M1)   Cursor / VSCode+Copilot / Zed (M5)       │
│  PostToolUse/Session…     RawEdit deltas + weak source hints       │
└─────────────┬───────────────────────────┬─────────────────────────┘
              │  trace-client SDK (fire-and-forget, spool, breaker)
              ▼  NDJSON over UDS  (loopback-HTTP fallback + token)
┌──────────────────────── trace daemon (Python) ────────────────────┐
│ ingest acceptor → ring buffer → durable batch writer  [SWAP SEAM] │
│ HotStore (SQLite WAL)   ChunkStrategy+Tracker   classify/          │
│ HumanEditDetector       confidence model        redaction+vault   │
│ NotesManager+rewrite hooks   hash-chain   /blame /summary /export  │
└─────────┬───────────────────────────────────────────┬────────────┘
          ▼                                             ▼
   Local SQLite (~/.trace/db)                   git notes (in repo)
          └──────────────────────┬──────────────────────┘
                                 ▼   one shared BlameResolver (trace-core)
        ┌────────────┬───────────────────────┬──────────────────┐
        ▼            ▼                       ▼                  ▼
   trace CLI    GitHub PR bot        Next.js dashboard     REST API
  (blame/...)  (notes + sync)        (4 team views)      (3rd party)
                                 ▲
                       optional cold FastAPI server (M4)
```

**Seven load-bearing contracts** hold this together. Freeze them carefully — everything else is swappable.

1. **CC0 `AuthorshipEvent` JSON Schema** — the published open standard every producer emits and every consumer reads.
2. **NDJSON ingest wire protocol** — UDS on POSIX / named pipe on Windows, loopback-HTTP fallback for sandboxed/Claude-Code clients, with two-phase ack.
3. **`ChunkStrategy` interface + `content_hash` spec** — `ast-norm-v1` (tree-sitter) / `linewin-v1` (fallback).
4. **`refs/notes/trace` schema** — append-only, content-addressed NDJSON, `cat_sort_uniq`-mergeable.
5. **Daemon REST/control API** — `/blame /summary /export /status /control/*`, consumed identically by CLI, bot, and dashboard.
6. **`trace://` content-addressed `events_uri`** — resolves hot → in-tree pack → cold server, host-neutrally.
7. **Per-event BLAKE3 hash chain + Ed25519-signed note checkpoints** — make the whole thing tamper-evident.

---

## 3. Core data model

**`AuthorshipEvent`** (the immutable unit; extends the PRD baseline):

`event_id` (= content hash), `timestamp`, `source`, `model`, `session_id`, `prompt_hash`, `prompt_excerpt` (redacted), `file_path`, `content_hash`, `content_range {start_line, end_line}`, `operation`, `human_modifications_after {char_count, line_count}`, `tool_calls[]`, `git_branch`, `repo_id`, `user_id`, `prev_hash` (chain), `schema_version`, `confidence`, `parent_event_id` (lineage).

**Source taxonomy** (CC0 enum — note `generated` is now first-class, see `[review-fix]` §8):
`human_keyboard`, `human_paste`, `cursor_autocomplete`, `cursor_agent`, `claude_code_tool_call`, `copilot_completion`, `copilot_agent`, `zed_agent`, `ai_paste`, **`generated`** (scaffold/codegen/lockfiles — neither AI nor human), `inferred` (backfilled heuristic, lowest confidence, never overrides a declared event).

**Confidence model** — one contract (`confidence/model.py`): `source → base_confidence`, and `conf_after_edit(base, edit_ratio)` that is monotonic-non-increasing along a lineage chain *except* when a new declared tool-call re-authors (resets to base). Rendered everywhere as the **same three-state badge**: `attributed ≥0.8` / `low-confidence (last-known) 0.4–0.8` / `unattributed <0.4`. `classifier_confidence` (capture certainty) and cryptographic `verification_status` are **separate orthogonal fields** — never conflated.

**Canonical serialization `[review-fix — pulled to M1]`** — lock **RFC 8785 (JSON Canonicalization Scheme)** (or a defined CBOR profile) *before any cross-machine hash is persisted*. `event_id`/`content_hash` must be byte-identical across independent implementations, or git-notes portability, cross-tier dedup, and the conformance suite all silently break. "Two machines hash the same event identically" is an **M1 exit criterion**, not an M3 nicety.

---

## 4. Chunk tracking — the technical heart

This is the single point of failure for the whole thesis (PRD: ">95% accuracy on real refactors or trust collapses").

- **Chunk identity = content-derived `ContentHash` of *normalized* node text.** *Not* tree-sitter node ids (verified: fresh on every reparse/clone — would break portability), *not* byte ranges (shift on any edit above). AST normalization drops comments/whitespace tokens and canonicalizes quotes/trailing commas, killing the #1 false signal: reformatters (prettier/gofmt).
- **Two-tier strategy behind a `ChunkStrategy` interface:** AST via **`tree-sitter-language-pack`** (MIT, pre-built wheels, all 5 v1 langs in one in-process dep) for TS/JS/Python/Go/Rust; a **content-defined line-window rolling hash** as the universal floor so `trace` never goes fully blind on configs/markdown/unsupported langs.
- **Adaptive granularity:** smallest named declaration as the unit, large bodies sub-chunked at statement level, tiny adjacent statements coalesced to a ~3-line / ~20-char floor (mirrors git's proven `-M` 20-char move threshold). Each chunk stores its enclosing-declaration path so the UI rolls up to function/file without re-parsing.
- **The diff-follow algorithm** (analogue of `git blame -C -M`, but over AST chunks) is a **staged matcher** run daemon-side at commit time, each stage emitting a `match_kind` + similarity that drives confidence decay and lineage:
  1. exact content-hash carry-over → 2. rename/move (hash match across files) → 3. fuzzy edit (token-shingle MinHash/Jaccard) → 4. split/merge resolution → 5. line-fallback for unparseable files.

**Accuracy posture & Plan B `[review-fix — critical]`.** External evidence (GumTree/difftastic-class tools) says a flat 95% on *messy* real refactors is aspirational. So we commit the fallback posture **now**, before measuring:

- Publish **per-`match_kind` accuracy budgets**, not one misleading aggregate (exact-carry ~100%; fuzzy-edit and split/merge lower).
- **Degrade gracefully:** when chunk confidence is low, surface *"AI-touched, attribution approximate"* rather than a false precise %. Useful and honest at 88%.
- **Conditional public claim:** "exact carry-over & renames >99%; heavy refactor lower, always confidence-flagged" — so a measured 90% is not an existential credibility event.
- **Seed a real-OSS refactor corpus in M1** (not M2) so we know the true number before building the launch narrative on it.
- A **CI accuracy gate** fails the build on `<budget` or any per-case regression; the corpus + metric ship as part of the CC0 standard so the number is independently verifiable.

---

## 5. Component map

| Component | Tech | Depends on | Phase |
|---|---|---|---|
| `trace-core` (shared lib: schema, hashing, BlameResolver, confidence, hash-chain) | Python (Pydantic v2) | — foundational | **M1** |
| `ChunkStrategy` (tree-sitter + line-window) + normalization profiles | Python + tree-sitter-language-pack + blake3 | trace-core | M1 |
| `ChunkTracker` (stages 1–2 M1; 3–5 M2) | Python + MinHash/LSH | ChunkStrategy | M1/M2 |
| Source classification engine (rules + feature-scoring) | Python (stdlib hot path) | trace-core, RawEdit | M1 |
| `HumanEditDetector` + canonical `edit_ratio` (**sole authority**) | Python (norm-Levenshtein) | ChunkStrategy, ChunkAttribution | M2 |
| Hash-chain + Ed25519 checkpoint service | Python (BLAKE3, Ed25519) | schema, store | M1 chain / M2 sign |
| Redaction engine (tier-1 detect-secrets, tier-2 gitleaks) | Python | ingest path | M1 / M2 |
| Prompt vault / key manager (AEAD, OS-keychain KEK/DEK) | Python cryptography + keyring | HotStore | M1 |
| HotStore (SQLite WAL) + migrations + retention sweeper | SQLite WAL | trace-core | M1 |
| Ingest acceptor (NDJSON/UDS) **[native-swap seam]** + ring buffer + durable writer | Python asyncio | wire protocol | M1 |
| `trace-client` SDK (framing, fire-and-forget, spool, breaker, `durable_seq`) | Python stdlib | wire protocol | M1 |
| Claude Code capture (hooks + transcript reconciler + session registry) | Python | trace-client, classify | M1 / M2 |
| NotesManager + RewriteHooks + refspec installer | Python over git plumbing | store, tracker, chain | M2 |
| **BlameResolver / ReconciliationEngine** (hot+notes+server, single shared) | Python | tracker, store, notes | M1 / M2 |
| Refactor eval harness + CI accuracy gate | pytest + corpus | ChunkTracker | M1 seed / M2 gate |
| **Product-telemetry emitter (opt-in, off by default)** `[review-fix]` | Python | daemon | **M1** |
| `trace` CLI (blame/summary/export/init/sync/status/verify/doctor) | Python (Typer + Rich) | trace-core, BlameResolver | M1→M3 |
| Query/control server (FastAPI on 127.0.0.1) | FastAPI + uvicorn | HotStore, BlameResolver | M1 / M2 |
| Daemon lifecycle & packaging (launchd/systemd, PyInstaller, self-update) | PyInstaller; pipx; brew | daemon | M2 |
| `trace-spec` repo (CC0 schema + notes + chunk algo) + conformance suite + **change-process + 2nd emitter** `[review-fix]` | Markdown + JSON Schema | frozen schemas | M3 |
| GitHub PR bot (`trace-bot` FastAPI: ack-enqueue, sticky comment, Check Run) | Python + FastAPI | trace-core, notes, ProvenanceSource | M3 / M4 |
| GitNotesSource + NotesFetcher + `trace ci` Action | Python; published Action | notes schema | M3 |
| Cloud sync server (events:batch ingest, delta pull, notes materializer, **server-side blame re-tracking** `[review-fix]`) | FastAPI + async SQLAlchemy + Postgres 16 + S3/MinIO | frozen schema, outbox | M4 |
| Analytics/aggregation (rollups, prompt→outcome join, **product metrics**) | Postgres mat. views + worker | cold store | M4 |
| Auth & tenancy (OAuth PKCE / device-flow / role mapping) + **identity reconciliation** `[review-fix]` | FastAPI + Authlib | sync server, bot identities | M4 |
| Next.js dashboard (4 PRD views + sync/consent) | Next.js App Router + Recharts | sync server REST | M4 |
| Editor plugins (Cursor + MCP, VSCode+Copilot, Zed) + `trace-capture-sdk` (TS/Rust) | TypeScript + Rust | Capture Plugin Contract, classify | M5 |
| Clipboard-origin browser extension (ChatGPT blind-spot bridge) | MV3 → loopback | wire contract | M3+ (decoupled) |
| Compliance export + Attestation Linker (SOC2 / EU AI Act) | Python; reviews API; Ed25519 | chain+verify, approvals | M3 linker / M6 export |
| Identity & SSO (SAML + OIDC + SCIM) + self-host OCI image + transparency anchor | FastAPI; one OCI image; Helm | auth, deploy-agnostic backend | M6 |

---

## 6. Monorepo layout

```
trace/
├── packages/
│   ├── trace-core/                 # Python — schema, canonical hashing, BlameResolver,
│   │                               #   confidence, hash-chain, enums. Gates everything.
│   ├── trace-daemon/               # Python (FastAPI+asyncio+sqlite3) — the local engine:
│   │                               #   ingest/ring/writer, HotStore, ChunkStrategy+Tracker,
│   │                               #   classify/, NotesManager, redaction, vault, telemetry.
│   ├── trace-client/               # Python (stdlib only) — thin plugin SDK, kept tiny.
│   ├── trace-capture-claude-code/  # Python — FIRST capture: hooks, session registry,
│   │                               #   tool_mapping, transcript reconciler, init/doctor.
│   ├── trace-cli/                  # Python (Typer+Rich) — primary v1 surface; own distribution.
│   ├── trace-compliance/           # Python — SOC2/EU-AI-Act report shaping, Attestation Linker.
│   ├── trace-capture-sdk/          # TypeScript — shared transport for VSCode-family plugins (M5).
│   └── trace-capture-sdk-rs/       # Rust — Zed/native client; home of native trace-ingestd if triggered (M5).
├── services/
│   ├── trace-bot/                  # Python (FastAPI) — GitHub PR bot; separate deployable.
│   └── trace-server/               # Python (FastAPI+SQLAlchemy+Postgres+S3) — cold tier + sync hub.
├── apps/
│   └── dashboard/                  # TypeScript (Next.js App Router) — 4 views + consent surface.
├── editors/                        # TS + Rust — per-editor plugins (M5): cursor/, vscode-copilot/, zed/.
├── browser-ext/                    # TS (MV3) — clipboard-origin bridge (M3+, decoupled).
├── actions/trace-action/           # The published `trace ci` GitHub Action.
├── spec/                           # CC0 — the OPEN STANDARD (own public trace-spec repo):
│                                   #   authorship-event.schema.json, content-hash-v1.md,
│                                   #   notes layout, chunk algo + reference vectors,
│                                   #   capture-plugin-contract.md, conformance/ runner.
├── deploy/                         # Dockerfile.selfhost (one OCI image), docker-compose, helm/ (M6).
└── bench/ + tests/                 # CI benchmark gate (5k ev/s p99), RSS soak, eval corpus,
                                    #   recorded Claude Code transcript fixtures, self-host smoke.
```

**Licensing:** CC0 on the *format* (`spec/`), Apache-2.0 on the *implementation*.

---

## 7. Cross-cutting decisions

The synthesis resolved every place two domains overlapped. These are binding.

| Topic | Decision |
|---|---|
| **Immutable/mutable split** | One CC0 `AuthorshipEvent` (immutable, append-only) vs `ChunkAttribution` (materialized view recomputed each commit). The foundational decision every domain inherits. |
| **Human-edit-ratio ownership** | `HumanEditDetector` is the **sole authority** computing canonical `edit_ratio` (norm-Levenshtein at chunk scope), daemon-side, incrementally, never at the AI-capture instant. Capture only *supplies* raw signals. A human edit is its **own event** with parent lineage → log stays append-only. |
| **Where classification happens** | **All** source classification is daemon-side (`trace/classify/`), shipped **M1** (needed day one to separate `human_keyboard` from `claude_code_tool_call`). Plugins are thin scavengers: forward `RawEdit` + weak `raw_source_hint`, decide nothing. |
| **Confidence unification** | One confidence contract; `classifier_confidence` and crypto `verification_status` are separate. Same three-state badge everywhere off the same number. |
| **Single BlameResolver** | **One** `BlameResolver` in `trace-core`, shared by CLI + bot + dashboard, so they can never disagree (divergence here is the exact failure the product exists to prevent). Precedence: uncommitted-hot > committed-note > server-backfill; content-hash tie-break; per-line confidence. Golden-file tests assert daemon and notes produce identical blame. |
| **Storage topology** | Four tiers, one-way materialization (§1). Blame/summary work fully offline against SQLite + notes; server is a strict opt-in superset. |
| **Who merges notes** | Note format is append-only content-addressed NDJSON sorted by `event_id`, so `cat_sort_uniq` merges are deterministic/lossless anywhere. Server is the **canonical** materializer but **not** a bare git remote; daemons sync *events* via idempotent REST, treat notes as a derived projection (keeps the editor hot path off git entirely). |
| **Shared auth** | Three GitHub credential flows, one per actor, FastAPI server as single token authority + tenancy point: dashboard = OAuth PKCE → server session; daemon = device flow → scoped machine token; PR bot = GitHub App installation tokens (only Apps write Checks API). SSO (M6) slots behind the same session abstraction. |
| **Latency budget + native-swap seam** | `<5ms p99` applies **only** to the raw-capture durable write (small SQLite insert); chunking/hashing/classification/notes are async off the hot path. Two-phase ack (transport-ack smooth + durability-ack via monotonic `durable_seq`). The **one** native-swap seam = ingest acceptor + ring buffer + writer, behind the NDJSON/UDS protocol + stable SQLite schema. Triggered by a CI benchmark gate (5k ev/s p99), **not** a guess. Python suffices through M5 for Claude Code's tool-call cadence. |
| **Local-first, prompts as secrets** | Enforced at the daemon: nothing leaves the machine unless sync is explicitly enabled per-repo (default off); prompt upload is a *second* finer opt-in (hash-only mode + org policy ceiling). Encrypted at rest, redacted client-side **before** transmit, excluded by default from notes (hash + bounded excerpt only) and **structurally** from public PR comments. |
| **Tamper-evidence from M1** | Per-event BLAKE3 hash chain in the SQLite write path from M1 (nearly free, brutal to retrofit); Ed25519-signed note checkpoints + `trace verify` in M2; optional external transparency anchor M6. |
| **Open standard = moat** | Publish event schema + notes layout + chunk algo **CC0** with a conformance suite at public launch. A neutral cross-tool format makes a native Cursor/Anthropic feature *most valuable when it emits the trace format* — converting competitors into ecosystem producers. |
| **Canonical repo identity** `[review-fix]` | Canonical `repo_id` = first-commit SHA (or a generated id in `.trace/manifest.json`), **never** the filesystem path. Used by HotStore routing, NotesManager, sidecar. Worktrees of one repo share provenance keyed by `repo_id + branch`. **M1 decision** (the hot-store schema depends on it). |
| **Identity reconciliation** `[review-fix]` | Local `user_id` is *provisional* (from `git config user.email`), later linked to a canonical trace identity once device-flow/OAuth (and M6 SSO) establish GitHub/SSO subjects. Mapping table `trace_user_id ↔ git emails[] ↔ github_login ↔ sso_subject` lives in the auth service; compliance export + dashboard key on the **canonical** identity. Provisional-vs-canonical model lands **M1** so early events are reconcilable, not stranded. |
| **Ingest authenticity** `[review-fix]` | The loopback-HTTP ingest path (Claude Code http hook, browser bridge) is a trust surface: any local process could POST a forged event. Require a per-session/per-daemon shared secret (0600 file the legit hook reads), strict Origin/Host validation (defeat DNS-rebinding), bind 127.0.0.1 only. Prefer UDS/named-pipe whenever the client can. Hash-chain proves integrity-*after*-capture; the token provides authenticity-*at*-capture. |
| **Product analytics** `[review-fix — critical]` | A small CC0 product-event taxonomy *distinct* from `AuthorshipEvents` (installed, first-blame, first-PR-comment, daemon-DAU, repos-onboarded, notes-fetched-by-collaborator). An **opt-in** daemon telemetry emitter (off by default, separate consent from sync, anonymized `install_id`, **never** code/prompt/path bytes) is the activation/engagement source — must land **M1** or dogfood/alpha activation data is lost forever. Team/growth metrics derived server-side from sync + bot-install events. Honest reconciliation with "we don't phone home by default": aggregate counts opt-in + server-derived for teams. |

---

## 8. Privacy, security & threat model

| Threat | Mitigation |
|---|---|
| Prompts leak company secrets | Local-first enforced; prompt upload a separate opt-in with hash-only mode + org ceiling; two-tier redaction client-side *before* transmit (detect-secrets fail-closed; gitleaks before any excerpt hits a note); AEAD at rest (OS-keychain KEK/DEK); notes carry hash + bounded excerpt only; **public PR comments structurally carry no prompt bytes**. |
| Provenance tampered to hide AI authorship | BLAKE3 per-event hash chain + Ed25519-signed note checkpoints; `trace verify` detects content edits, chain breaks, bad signatures, and **strip-detection**; optional external transparency-log anchor (M6). |
| Forged events at the ingest surface `[review-fix]` | Per-session token + Origin/Host validation on loopback HTTP; prefer UDS. |
| Capture slows the editor | Fire-and-forget + ring buffer + circuit breaker; transport-ack at kernel-buffer latency regardless of language. |
| Daemon compromised | Runs as user (not root); minimal surface; encrypted prompt vault yields only ciphertext from a stolen `~/.trace/db`. |

"**No clipboard monitoring**" is a published guarantee — paste is classified by event *signature*, not content inspection. Org Policy Engine decouples *require-capture* (mandatory events) from *content visibility* (redaction floor) so compliance and privacy both win. Strictest tier adds zero-knowledge prompt mode (client-key encryption the hosted server cannot read) + SQLCipher whole-DB option.

---

## 9. The open standard (`trace-spec`)

A published file is not a standard. To make the moat real `[review-fix]`:

- **CC0** `AuthorshipEvent` schema + `refs/notes/trace` layout + `content_hash` algorithm + reference vectors + confidence model, in a dedicated public `trace-spec` repo.
- **Conformance suite:** a golden corpus any implementation must reproduce *identical `content_hash` + chunk lineage* against.
- **A written change-process** (how `schema_version` increments, deprecation policy, backward-compat rules) — shipped at M3, not improvised later.
- **A second, independent reference emitter** (even a tiny third-party-style script) run through the conformance suite at M3 to prove the format is portable, not just "whatever `trace` happens to output."
- **Move the vendor-neutral-governance conversation to M4** (when teams adopt), not M6 — neutrality *is* the moat, so deferring it contradicts the thesis.
- Define what "**trace-conformant**" legally means before encouraging anyone to claim it.

---

## 10. 6-Month roadmap

Re-derived for the locked decisions (Python daemon + Claude Code first, **not** the PRD's Rust + Cursor first). `[review-fix]` marks items added by the adversarial critique.

### M1 — Python daemon + Claude Code capture + blame (dogfood)
**Deliverables**
- `trace-core`: `AuthorshipEvent` Pydantic schema v0 + canonical hashing (BLAKE3) + per-event hash chain.
- **`[review-fix]` Lock canonical serialization (RFC 8785 / CBOR profile) + exact normalization bytes; cross-machine hash-equality test in CI.**
- **`[review-fix]` Canonical `repo_id` derivation + worktree handling; provisional `user_id` → canonical-identity contract.**
- `ChunkStrategy`: AST for Python/TS/JS via tree-sitter + line-window fallback; `content_hash = ast-norm-v1`.
- `ChunkTracker` stages 1–2 (exact carry + move/rename).
- Source classification engine (rule layer + Claude-Code sources), with **`generated`** as a first-class enum value `[review-fix]`.
- Confidence model + three-state render hint.
- HotStore: SQLite WAL schema + PRAGMAs; prompt fields AEAD-encrypted (OS-keychain KEK/DEK).
- Ingest acceptor (NDJSON/UDS) + ring buffer + durable batch writer **[native-swap seam established]**; **per-session ingest token on the HTTP fallback `[review-fix]`**.
- `trace-client` SDK (fire-and-forget + spool + circuit breaker + two-phase ack).
- Claude Code **live** capture: `PostToolUse`/`SessionStart`/`UserPromptSubmit` hooks (native http + command-hook spool fallback); session registry (model cached at `SessionStart`, joined by `session_id`); `tool_mapping` from `structuredPatch` hunks.
- Tier-1 in-process redaction (detect-secrets, fail-closed).
- `trace` CLI skeleton: `init` / `status` / `blame` (hot-only); `trace doctor` (settings.json hook merge + synthetic round-trip).
- **`[review-fix]` Opt-in product-telemetry emitter (off by default) + the CC0 product-event taxonomy.**
- **`[review-fix]` Seed a real-OSS refactor eval corpus to learn the true accuracy number before M2.**

**Milestone:** `trace blame` on `trace`'s own repo correctly attributes Claude-Code-authored vs human-typed lines in a live session; raw-capture write p99 under the editor budget; daemon RSS < 100MB in soak; **two machines hash the same event identically**. *Dogfood: the team uses `trace` on `trace`.*

### M2 — Accuracy + git notes + summary + sidecar (private alpha, ~10 devs)
**Deliverables**
- `ChunkTracker` stages 3–4 (fuzzy MinHash edit + split/merge — where the accuracy number is won) + Go/Rust grammars.
- Refactor eval harness + **CI accuracy gate with per-`match_kind` budgets** `[review-fix]` (fails on `<budget` or per-case regression).
- `HumanEditDetector` (sole authority for `edit_ratio`) + reattribution thresholds.
- **`[review-fix]` Intra-session out-of-band edit coverage: pull the opt-in `FileChanged` watcher (or a git pre-commit reconciliation pass diffing working tree vs last-known hashes) into M2; make "uncommitted, possibly-stale" an explicit blame state.**
- Generated/scaffold/binary edge-case handlers, **wired into the classifier stamp + notes schema + confidence table + render contract** (not just chunk metadata) `[review-fix]`.
- NotesManager: `refs/notes/trace` per-commit summary (append-only content-addressed NDJSON) + size caps; `refs/notes/trace-events` opt-in. **Per-chunk record carries `match_kind` / `is_last_known` so the three-state semantics survive the SQLite→notes projection** `[review-fix]`.
- RewriteHooks: post-commit + post-rewrite (+ explicit cherry-pick/squash union) + post-merge reconcile; `notes.rewriteRef`/`rewriteMode=cat_sort_uniq` installer. **Squash union preserves per-chunk `prompt_hash`/`session` lineage, not just source/model** `[review-fix]`.
- Ed25519-signed note checkpoints + `trace verify` (content + chain continuity + signature + strip-detection).
- Tier-2 gitleaks deep-scan (gates the first `prompt_excerpt` written to a note).
- Claude Code transcript reconciler: `parentUuid` causal walk for exact prompt assignment; `gitBranch` per record; backfill pre-install sessions (`source=inferred`).
- `BlameResolver`: hot + committed-notes reconciliation with per-line confidence.
- `trace summary` + the `--json` v1 contract (the exact shape bot + CI consume) + `trace sync`.
- `.trace/manifest.json` sidecar + `trace setup` (applies fetch/push refspecs — notes are **not** synced by default) + post-checkout bootstrap.
- Metrics + `trace doctor` (p99, queue depth, RSS, WAL size, false-attribution counters).
- Packaging: PyInstaller binary + launchd/systemd `--user` service.

**Milestone:** ChunkTracker scores **≥ its per-kind budget** on a frozen ground-truth corpus (moves, splits, renames, formatter runs, squashes) in CI; 10 alpha devs clone each other's repos and `trace blame` works from notes alone after `trace setup`; `trace verify` detects a tampered/stripped note; mixed-author rendering ("60% you, 40% claude") is stable across trivial edits.

### M3 — Public launch: PR bot (public repos) + CC0 spec v1 + Show HN
**Deliverables**
- `trace-spec`: freeze + publish CC0 `AuthorshipEvent` schema, notes layout, `content_hash` algorithm + reference vectors, confidence model. **+ spec change-process (versioning/deprecation) + a second independent reference emitter through the conformance suite** `[review-fix]`.
- Conformance suite (golden corpus → identical `content_hash` + chunk lineage; **the three-state/`match_kind` semantics are a conformance assertion** `[review-fix]`).
- GitHub App + `trace-bot` FastAPI webhook service: HMAC verify + `X-GitHub-Delivery` dedupe + fast-ack-then-enqueue + durable queue + idempotent workers.
- `GitNotesSource` + `NotesFetcher` (zero-config bot-side notes fetch by head SHA) + the `trace ci` GitHub Action.
- `ReportBuilder` + sticky update-in-place PR comment (hidden marker, 65k budget, authorship chart + file heatmap + flagged low-human-edit files + an explicit **"excluded as generated"** line + an **"unattributed/approximate"** rule `[review-fix]` + `trace blame` deep links) + **neutral (non-blocking)** Check Run.
- `ConfigResolver` (`.trace/config.yml` from PR head, JSON-Schema validated).
- **Prompts structurally absent on public repos** (defense-in-depth: `GitNotesSource` carries no prompt bytes).
- CLI hardening: lazy-import cold-start tuning + CI smoke benchmark (cold `trace blame` < ~150ms), paging for large files/long histories, `trace export`, `--show-prompts` with redaction.
- `EventsUriResolver` (`trace://` chain) + in-tree event packs for self-contained public repos.
- `ContentFingerprintIndex` (in-repo cross-commit origin following).
- Attestation Linker (PR approval → signed human-review attestation). *Note: its identity dependency is satisfied minimally here; full role-mapping arrives M4 — see sequencing note.*
- Published threat model + "no clipboard monitoring" guarantee; clipboard-origin browser extension (decoupled, hash-prefix only).
- `uv tool install` + standalone binaries + Homebrew tap; **CI benchmark gate (5k ev/s p99) that will later trigger the native-acceptor decision**.
- **`[review-fix]` Notebook decision in the spec before freeze: either a cell-addressed `content_range` variant (`cell_id` + intra-cell range) or explicitly scope `.ipynb` to file-level provenance in v1 — and say so.**

**Milestone:** Show HN — anyone installs the GitHub App on a **public** repo (with the `trace` Action or zero-config notes fetch) and gets a correct, **prompt-free** authorship PR comment + neutral check; an independent third party runs the conformance suite and reproduces identical `content_hash` on the golden corpus; the spec is live CC0.

### M4 — Teams: hosted/self-host sync server + dashboard + private-repo bot
**Deliverables**
- Cloud sync server (FastAPI): `POST events:batch` (idempotent by `event_id`, cursor-based, ack-after-durable-write) + `GET events?since_cursor` delta pull.
- Cold event store: Postgres 16 (monthly partitions, GIN/btree) metadata/index + S3/MinIO content-addressed encrypted payloads (object-first then index-commit ordering).
- Server-side notes materializer/merger (canonical; rebuilds correct notes even if a teammate never synced).
- **`[review-fix]` Server-side blame re-tracking: run `trace-core`'s ChunkTracker over fetched historical trees for commits older than the 30-day hot window — OR document the durability floor honestly ("full line-level blame guaranteed within 30 days / wherever an in-tree note or event-pack survives; older commits fall back to the per-commit note summary"). Pick one; don't imply server-backfill silently covers it.**
- Auth & tenancy: GitHub OAuth PKCE (dashboard session) + device-flow machine token (daemon) + membership→role mapping; single app-layer tenant guard. **+ the identity-reconciliation mapping table** `[review-fix]`.
- Next.js App Router dashboard: the 4 PRD views (authorship trends / per-engineer usage / **prompt→outcome** / model comparison) as server components feeding client Recharts islands; per-repo "what is synced" consent surface. **Per-engineer + prompt→outcome views consume the M1 product-telemetry + the server-derived metrics** `[review-fix]`.
- Analytics/aggregation: rollup tables + prompt→outcome join (chunk-survival × git history) + materialized views; role-based prompt redaction enforced server-side.
- `SyncClient` (opt-in per-repo; redaction client-side **before** transmit; hash-only mode) + daemon outbox.
- Org Policy Engine (`.trace/policy.json`: require-capture / redaction floor / org-lockable fields).
- PR bot private half: `SyncServerSource` + private-repo installation + prompts `<details>` block (private-only) + threshold-based **gating** Check Run.
- Server-side `ContentFingerprintIndex` (opt-in cross-repo origin following).
- Immutable server-side audit log (hash-chained) for policy changes / exports / key rotations / access grants.
- One-command self-host (same OCI image as hosted; docker-compose: server+Postgres+MinIO+worker; CI runs the self-host stack as a smoke test).
- **`[review-fix]` Open the vendor-neutral-governance conversation (moved earlier from M6).**

**Milestone:** a team with a private repo enables sync, sees the 4-view dashboard populated from real sessions, gets a private-repo PR comment with redacted prompts + an optional gating check; the **same** OCI image runs the whole stack on-prem with zero cloud dependency; cross-tenant access returns 404 in integration tests; nothing uploads unless explicitly enabled.

### M5 — Editor expansion: Cursor / VS Code+Copilot / Zed + cross-tool normalization
**Deliverables**
- Capture Plugin Contract v1 published (`RawEdit` / `CompletionLifecycle` / `AgentAction` / `Heartbeat` over UDS/NDJSON) as part of the CC0 standard.
- `trace-capture-sdk` (TS) + `trace-capture-sdk-rs` (Rust) — implement the wire protocol + spool once.
- Cursor extension (`onDidChangeTextDocument` + competing `InlineCompletionItemProvider`) + optional `trace-cursor` MCP context-server (authoritative `cursor_agent` labels, opt-in, upgrade-only).
- VS Code + Copilot extension (shadow `InlineCompletionItemProvider` + suggestion-text byte-matching; **heuristic by necessity — no Copilot acceptance API; surface an honest per-repo coverage metric, never silently credit a human**).
- Zed context-server + LSP shim (coarse save-diff + agent-action capture; line-precision deferred to upstream Zed buffer APIs).
- Classification scoring layer + full source enum activated.
- Cross-tool normalizer (`raw_source_hint` → shared enum; identical semantics; forensic hint retained). **Reconcile differing per-tool confidence *meanings* so model-comparison analytics compare comparable numbers** `[review-fix]`.
- Dashboard + PR-bot render the additional source labels (no new architecture).
- **NATIVE-SWAP DECISION POINT:** if the benchmark gate shows ingest p99 regressing under newly-arriving keystroke-rate sources, build the Rust/Go `trace-ingestd` replacing **only** acceptor+ring-buffer+writer behind the wire protocol — zero plugin/schema changes. Decided on the number, not judgment.

**Milestone:** one dashboard shows authorship for the same engineer across Claude Code + Cursor + Copilot normalized into one vocabulary; Copilot capture reports a measured, honestly-stated coverage rate; the native-swap go/no-go is decided on the benchmark; the daemon, SQLite schema, and notes format are **unchanged** by any new editor.

### M6 — Enterprise: SSO, on-prem, SOC2 prep, compliance export, audit
**Deliverables**
- SAML 2.0 + OIDC SSO + SCIM provisioning behind the existing session abstraction.
- Optional Postgres RLS (defense-in-depth) + zero-knowledge prompt mode (client-key-encrypted prompts the hosted server cannot read).
- `trace export --compliance=soc2` (CC8.1 change-management evidence) + `--compliance=eu-ai-act` (Annex IV: AI-authorship % over a date range, model+version inventory, human-oversight attestations) — timed ahead of the EU AI Act high-risk deadline; Ed25519-signed, offline-re-verifiable.
- Compliance reports embed chain checkpoints + link change-sets to real PR-approval attestations (Attestation Linker from M3).
- Single self-hostable OCI image + data residency (region, not app sharding) + Helm chart.
- Optional external transparency-log anchor (Merkle / Rekor-style; inclusion + consistency proofs).
- Bot + server audit logs as compliance/audit-export sources; GitHub Enterprise Server / on-prem bot support.
- SQLCipher whole-DB at-rest option; org-lockable required-check enforcement.
- **Public REST API for third-party integrators** (versioning + authn + rate-limit), distinct from the dashboard's internal REST `[review-fix — PRD Phase 3 surface]`.
- Pursue a vendor-neutral governance home for `trace-spec` (the neutrality *is* the moat).

**Milestone:** a SOC2-prep customer runs `trace export --compliance=soc2` over a quarter and an auditor consumes it as CC8.1 evidence with human-review attestations tied to real GitHub approver identities; the entire stack runs air-gapped on-prem in a chosen region from one OCI image with SSO; a compliance report re-verifies offline against the org public key.

---

## 11. Top risks

| # | Risk | Severity | Where defended |
|---|---|---|---|
| 1 | **Chunk-tracking accuracy below trust threshold** on real refactors — the named trust-collapse risk, single point of failure. | Critical | AST-normalized hashing + content-derived identity + staged matcher; **per-`match_kind` budgets, graceful degradation, conditional claim, corpus seeded M1, CI gate M2** (§4). |
| 2 | **Privacy / a single prompt leak** — catastrophic for an audit product, blocks enterprise. | Critical | Defense-in-depth: local-first enforced, separate prompt opt-in, two-tier redaction, AEAD at rest, notes hash-only, **public PR comments structurally prompt-free** (§7–8). |
| 3 | **Latency-in-Python** can't guarantee sub-5ms p99 at keystroke rates (M5 editors). | High (low M1–M5) | Budget scoped to the SQLite insert; two-phase ack; one published native-swap seam; benchmark-gated, measured trigger (§7). |
| 4 | **Editor cold-start** — 3 of 4 editors deny a clean authorship signal; Copilot/VS Code is the volume. | High | Invert the assumption: daemon-side classifier (M1) is load-bearing, plugins are scavengers; Copilot honestly admits coverage; Claude-Code-first proves the pipeline on the one clean signal first (§7). |
| 5 | **Vendor competition** obsoletes the tool. | High | The moat is the **CC0 open standard + conformance suite**, not the tool; native features become most valuable when they emit the format (§9). |
| 6 | **Git notes silently lost** on cherry-pick/squash/merge, and `refs/notes/*` not fetched by default — zero provenance exactly at the review surface. | High | Belt-and-suspenders rewrite survival + content-hash (not SHA) as the durable key + refspec onboarding + server-side materializer safety net; cold-clone path an M3 release gate. |

---

## 12. Two critical gaps the review forced (read these)

1. **The measurability product could not measure itself.** All 9 domains produced *system* telemetry (p99, RSS, queue depth) but **no product analytics** (activation/engagement/growth funnels) and — worse — no collection path reconciled with "nothing leaves the machine by default." Fixed by an **opt-in product-telemetry emitter in M1** + a CC0 product-event taxonomy + server-derived team metrics. If this slips past M1, M1–M3 activation/retention data is unrecoverable.

2. **The 95% accuracy bet had no Plan B.** Treated as a defended invariant, but external evidence says a flat 95% on messy refactors is aspirational. Fixed by committing the **fallback posture now** (§4): per-kind budgets, graceful "approximate" degradation, a conditional public claim, and seeding the real corpus in **M1** so we learn the true number before staking the launch narrative on it.

Both are now first-class in the roadmap above.

---

## 13. Open questions still to settle

- **Inferred-source precision** — heuristics for the general backfill case are asserted, not specified, and unmeasured; add an inferred-source precision eval.
- **ChatGPT paste residual** — the browser bridge covers allowlisted *browser* copies only, not the ChatGPT desktop/mobile app or cross-device; quantify and surface the residual as a coverage metric rather than implying full coverage.
- **Cross-tool confidence semantics** — a Cursor 0.9 and a Copilot 0.9 don't mean the same thing; the M5 mapping table needs an actual calibration design before cross-tool model comparison is trustworthy.
- **Public API shape** — REST chosen for the dashboard; the external-integrator API (versioning, authn, rate-limit) is scoped to M6 but its surface/GraphQL question is still open.

---

## 14. Recommended next step

M1 is the critical path and everything gates on `trace-core`. A sensible kickoff slice, in order:

1. `trace-core`: `AuthorshipEvent` schema + **canonical serialization (RFC 8785)** + BLAKE3 hashing + hash chain + the cross-machine hash-equality test.
2. HotStore (SQLite WAL) + the ingest acceptor/ring/writer seam + `trace-client` SDK.
3. Claude Code capture (hooks + session registry + `tool_mapping`) → the first real events.
4. `ChunkStrategy` (tree-sitter) + `ChunkTracker` stages 1–2 + the seeded refactor corpus to learn the true accuracy number early.
5. `trace blame` (hot-only) + `trace init`/`doctor` → **dogfood `trace` on `trace`.**

I can scaffold this M1 slice (monorepo skeleton, `pyproject`, `trace-core` schema + hashing, and a runnable daemon stub) on request.

---

*Architecture synthesized from a 9-domain multi-agent design pass with an adversarial completeness review; all `[review-fix]` items trace to that review. The format spec (`spec/`) is the CC0 standard; the implementation is Apache-2.0.*
