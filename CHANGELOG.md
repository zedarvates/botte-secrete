# Changelog

All notable changes to Botte Secrète. This project follows [SemVer](https://semver.org).

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
