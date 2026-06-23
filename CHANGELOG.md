# Changelog

All notable changes to Botte Secrète. This project follows [SemVer](https://semver.org).

## v1.4.0 — 2026-06-23

Security + determinism iteration. A neuro-symbolic taint analyzer wired into
`/checkup` and CI; scoped docs management for multi-component projects; and the
OR-Tools-inspired determinism program — exact computation (knapsack, solvers,
rule-based NLP) replacing LLM reasoning for structured decisions. 0 cloud tokens
throughout.

### Added
- **Context budget** (`skills/context_budget/`) — the OR-Tools principle applied to
  the always-on cost: choosing *which* skills/docs to load is an exact **0/1
  knapsack** (maximize relevance while summed tokens ≤ budget), not an LLM
  "what's relevant" call — deterministic stdlib DP, 0 cloud tokens, optimal not
  greedy. Ranks with `skill_finder`, then knapsacks; on this repo a task loads
  ~4 skills (~2k tok) instead of the whole ~36-skill catalog (~15k tok). New
  `context_budget` CLI + MCP tool; generic `knapsack(items, budget)` engine.
- **Deterministic solvers** (`skills/solvers/`) — the OR-Tools family in stdlib,
  completing the determinism program. `assign_balanced` spreads (name, cost) tasks
  across workers/backends to minimize the makespan (LPT greedy); `bin_pack` packs
  items into the fewest bins of a capacity (first-fit-decreasing); `schedule`
  topologically orders plan steps under precedence `deps` into a sequence **+
  parallel waves** (cycle-detecting). Exact/repeatable, 0 cloud tokens — no LLM
  "figure out the order/assignment" call. New CLI + `schedule_plan`/`assign_work`
  MCP tools.
- **Deterministic NLP** (`skills/nlp_deterministic/`) — classify and extract from
  text without an LLM (the NLP half of the determinism program). `classify(text,
  intents)` scores intents by keyword recall blended with a local hash-embedding
  cosine; `extract_entities(text)` regexes urls/emails/IPs/paths/env vars/flags/
  numbers; `keywords(text)` is stopword-filtered frequency. Deterministic, instant,
  0 cloud tokens. New CLI + `nlp_classify`/`nlp_extract` MCP tools — a 0-token
  triage/routing layer instead of asking a model to classify/extract.
- **Security in `/checkup` (and CI)** — the canonical checkup now runs the
  taint/data-flow analyzer, reports a `security` summary (count, high-severity,
  by-CWE, top findings), promotes high-severity findings to drift, and surfaces a
  🛡️ Security section in the PR comment — so security rides into CI through the
  existing `botte-pr-checkup` workflow with no extra wiring. 0 cloud tokens.
- **Docs steward** (`skills/docs_steward/`) — scoped documentation map for
  multi-component projects (server + client + tools + …). Detects components
  (manifest / known name / code; monorepo containers expand to children),
  classifies every doc as global vs component-scoped, and frames token cost so a
  coder bounded to one component loads only its docs + linked globals — not every
  other component's. `.md` = LLM-facing (load), `.html` = human reference (linked).
  `index --write` drops a per-component `DOCS.md` (confirm-gated). New `map`/`index`
  CLI + `docs_map` MCP tool. 0 cloud tokens.
- **Docs lifecycle** (`docs_steward/lifecycle.py`) — finished work shouldn't keep
  costing tokens. `tasks` finds checkbox plans/TODOs and counts open vs done + the
  token waste of done items; `prune` strips done items (preserving them in
  `.botte/archive/`) and archives fully-done plans; `reports` keeps the N most
  recent `.botte` reports and archives the rest. Prune/archive are confirm-gated
  (preview by default); read-only summary via the `docs_lifecycle` MCP tool.
- **Taint / data-flow security analyzer** (`fallow_like/analyzers/taint.py`) —
  neuro-symbolic, local-first, inspired by RepoAudit/DeepAudit. The symbolic pass
  (Python `ast`, 0 tokens) traces attacker-controlled sources (argv, env, request,
  input) into dangerous sinks (subprocess/eval/exec, SQL, pickle/yaml, urlopen) and
  flags insecure-by-default calls, each CWE-tagged (78/89/94/502/918). An optional
  neuro pass (`--judge`) asks a LOCAL model to confirm candidates (0 cloud tokens).
  New `taint` CLI subcommand + `security_scan` MCP tool; wired into health scoring
  as a hard signal and into the SARIF/markdown outputs.

### Fixed
- **Deterministic LLM tests** — the live-backend branches of `docgen`,
  `auto_router` (fusion vote) and `prompt_improver` asserted on real local-model
  output, so a slow/timing-out model (e.g. a 12B coder) made the suite flaky. They
  now exercise the same code paths against a stubbed local client with a canned
  reply (the shared `LocalLLMClient` is patched at the class level + a forced
  reachable backend), so the suite is green regardless of which model is loaded —
  while still covering the local-first, 0-cloud-token contract.

## v1.3.0 — 2026-06-20

Autonomy iteration — the conductor now *runs* safe plans, ingest gains real local
semantic recall, and every PR gets a local-first checkup. 0 cloud tokens throughout.

### Added
- **GitHub Action — checkup on PR** — `🧦 Botte Checkup (PR)` workflow runs the
  canonical `/checkup` on every pull request and posts (or updates in place) a single
  verdict comment via `gh`. New `checkup --pr-comment` flag + `format_pr_comment()`
  (pure, carries a stable marker). 0 cloud tokens, no extra deps; reusable by any
  project that deployed botte-secrète.
- **Real local embeddings for ingest** — `ingest`/`search` now auto-resolve a local
  `/v1/embeddings` endpoint from the backend registry (any reachable backend exposing
  an embedding model → real semantic vectors), falling back to the deterministic hash
  vector when none is available. New `resolve_embed()`, `--embed-url`/`--embed-model`
  flags, `embed_url`/`embed_model` on the `ingest_source` MCP tool; the result reports
  `embed: endpoint|hash`. 0 cloud tokens either way.
- **Conductor executor** — the conductor can now *run* a plan, not just produce it.
  Read-only analysis steps run unattended; mutating/cloud steps are confirm-gated;
  steps with an unfilled `<placeholder>` are skipped. New `--execute`/`--confirm`/
  `--dry-run` CLI flags and an `execute_plan` MCP tool. 0 cloud tokens for the safe
  steps; injectable runner keeps it fully unit-tested.

### Removed
- 4 genuinely-unused symbols flagged by our own dead-code analyzer (`check_tool`,
  `CodeFingerprint.is_same`, `SkillInfo.token_cost`/`qualified_name`).

## v1.2.0 — 2026-06-20

Cost-visibility iteration — every correction now comes with a price tag.

### Added
- **`cost_estimator`** — estimate any task or fix as **tokens · model · money ($) ·
  time**, reusing the tiered cost model (local = free, cloud = billed/faster).
- **`fix`** — list a project's correctable issues (confirmed dead code, duplication,
  stale directive refs), each with its cost to apply and a grand total. Plan-only
  (never edits code).
- **`trends`** — snapshot audit metrics over time and show the delta since the
  previous run (directive score, duplication, LOC, always-on cost, fixes).
- **`dashboard`** — one timestamped HTML view assembling routing savings, trends,
  metrics and the cost of outstanding fixes.
- MCP: `estimate_cost`, `fix_plan`, `trends_show`, `dashboard` (26 tools total).

### Tests
- +cost_estimator (8), trends (4), dashboard (2). Suite: **248/248**.

## v1.1.0 — 2026-06-20

Quality + capability iteration.

### Fixed
- **`dead_code` false positives** — the analyzer now builds a global identifier-
  occurrence index across all source (strings included), so symbols used via MCP
  dispatch tables, `__all__` re-exports, `getattr`/string dispatch and framework
  override callbacks (`do_POST`, `handle_data`, `activate`, …) are no longer
  flagged. On this repo: **267 → 11** findings; self-audit health 59 → **75 (B)**.

### Added
- **Expanded machine-agent** (`cluster.agent`): read-only `gpu` (nvidia-smi) and
  `processes` (LLM-related) diagnostics; richer operator maintenance-command
  example (ollama list, restart ComfyUI, repo fast-forward, cache purge).
- Tests: `fallow_like.test_dead_code` (5), agent maintenance coverage. Suite: **230**.

## v1.0.0 — 2026-06-20

First stable release. A local-first, self-improving system that makes any project
cheaper to work on: it discovers itself, routes work to the cheapest capable
backend, acts locally, measures its own outcomes, and adapts its routing.
**31 modules across 6 layers · 22 MCP tools · 225 tests** (`python scripts/run_tests.py`).

### The system, in layers
- **SENSE** — `directives_audit`, `metrics`, `infra_advisor`, `fallow_like`,
  `skill_finder`, `llm_backends` (machine/cluster/task understanding).
- **DECIDE** — `auto_router` (effort→tier, local↔cloud + fusion), `tiered_router`,
  `local_router`, `conductor` (goal → ordered capability plan), `cluster`
  (homelab scheduling), `preflight` (prefer-local policy + per-turn hook).
- **ACT** — `llm_mcp` (22 MCP tools), `ingest` (scrape + Qdrant), `docgen`
  (local-draft → cloud-refine + session review), `app_test` (OculiX image-match
  GUI testing + HTML post-mortem), `prompt_improver`, `mousquetaires`/`cardinal`.
- **REMEMBER** — `response_cache`, `code_fingerprint`, `vector_protocol`,
  `ultra_compact`, `loader`, `cache`.
- **GOVERN** — `capabilities` (self-model + curator), `checkup` (canonical audit
  + drift), `control_loop` (measure → adapt routing), `report` (timestamped
  .md/.html audits), `clarification`, `skill_project_optimizer`.
- **DEPLOY** — `bootstrap` (one-command install into any project).

### Highlights
- **Deploy into any project** (`bootstrap`): wires the `botte-llm` MCP server,
  the OculiX visual-control MCP server, the prefer-local policy + preflight hook,
  and writes `.botte/config` — non-destructively.
- **Local-first routing**: cheap work (classification, extraction, summaries,
  tool/skill search, prompt structuring, doc drafts) runs on local models for
  **0 cloud tokens**; only hard reasoning escalates. Cloud providers (DeepSeek,
  GLM, Nemotron, Grok, Gemma) via OpenRouter or native keys.
- **Self-improving**: `control_loop` measures routing outcomes and tunes the
  effort→tier thresholds the router reads live.
- **Homelab as a resource** (`cluster`): spread work to idle machines (LRU);
  safe, operator-approved, confirm-gated maintenance delegation.
- **Local-first GUI testing** (`app_test` + OculiX): JSON spec + button images →
  runnable test + HTML post-mortem (logs/screenshots), 0 cloud vision.
- **Consultable audits** (`report`): every audit savable as a timestamped
  `<name>_<date>_<time>.md/.html` under `.botte/reports/`, browsable any time.
- **Windows-ready**: UTF-8 everywhere; runs on a default Windows console.

### Notes / known follow-ups
- The `dead_code` analyzer over-reports on dynamically-imported code (health
  scoring is confidence-weighted to compensate).
- Cloud routing requires an API key (fully local otherwise).

See the full module table and roadmap (P0–P30) in the [README](README.md).
