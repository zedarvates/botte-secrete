# Changelog

## Unreleased

### Added
- Idempotent `botte.quality-outcome/v1` envelopes for partial and verified
  execution results, with the local harness as the first live adapter. Only
  externally evidenced verdicts enter the shadow Quality Compass ledger.
- Auto-router outcome adapter for private, replay-safe `PARTIAL`, `FAIL`, and
  `ABSTAINED` facts; backend returns remain unverified and cannot promote labels.
- Strict `botte.agent-run/v1` manifests shared by Codex MCP and the Hermes
  function bridge, rejecting raw-output fields and agent self-labels.
- Primary GitHub CI matrix outcome adapter with replay-safe verified envelopes
  and a separate sanitized artifact that exposes state, reason, and the next
  safe action without run IDs, fingerprints, paths, or evidence details.
- Accessible Quality Compass dashboard card with a fluid state/reason/next-action
  view, progressive local evidence, route comparison, freshness and human-gate
  states; public snapshots disclose no local task or evidence material.
- Leakage-resistant shadow routing benchmark for deterministic, k-NN, and the
  existing `binary_router` micro-NN. It uses a shared temporal holdout, rejects
  exact-task and family leakage, separates routing/model/harness quality, and
  emits an explicit `collect_more_data` report when verified evidence is
  insufficient; fixtures cannot manufacture a winner or grant `ACT` authority.
- Shadow-only Quality Compass: a project-local verified-outcome ledger, duplicate-
  resistant hashed task features, explainable k-NN advice, `botte qa`, and lazy
  MCP tools (`qa_status`, `qa_advise`, `qa_record`). Raw task text is not stored,
  model self-reports are rejected as labels, and high-risk work keeps a human gate.
- Governed, per-project Memory Hub with provenance, lifecycle, visibility,
  sensitivity, expiry, versioning, and lazy MCP tools.
- Live loopback dashboard plus a sanitized, gated GitHub Pages artifact built
  from observed test summaries instead of hard-coded counters.
- Micro-NN grounding roadmap with G0-G3 maturity levels, per-model label
  sources and activation gates, plus a freeze on new models until the existing
  inventory is grounded or removed.
- Verified automatic-oracle labels for reversible compression and real response
  cache hit/miss outcomes, with stable deduplication and no raw content storage.

### Changed
- PR checkup now marks machine-local MCP wiring as not applicable on the
  ephemeral GitHub runner, while preserving the actionable local drift warning.
- Security scanner high-signal Python findings now require the regex match to
  start in executable code, eliminating self-matches in signature catalogs,
  docstrings, comments, and installation guidance without hiding real calls.
- Ground `binary_router` on explicit verdicts: automatic local returns/failures are
  unlabelled observations, executed routes expose a `feedback_id`, and the new
  `route_feedback` MCP tool appends the auditable local/cloud verdict.
- Capture `binary_router` in shadow mode for every comparable non-forced route,
  including heuristic local/cloud decisions, while preserving decision-source,
  confidence, and whether the belt actually acted.
- `/checkup` now separates observations from verified labels and keeps training
  and activation blocked below their 50/2,000 verified-sample gates.

### Security
- Require host-matched HTTPS endpoints and tokens for non-loopback cluster
  delegation; remove shell execution from README command validation.
- Keep local Memory Hub content and machine configuration out of public
  dashboard artifacts, with exact-fingerprint Gitleaks fixture exclusions.

## v1.9.0 (2026-07-14) — Loop Optimizer

### Added
- Deterministic Loop Optimizer: budgets, stop conditions, progress evaluation,
  failure signatures, append-only ledger, exact cache and minimal context.
- Optional, fail-closed Needle tool-router experiment with a 240-case bilingual
  evaluation corpus and measurable activation gate.
- Lazy MCP commands: `loop_decide`, `loop_explain`, `loop_record`, `loop_stats`.
- Local loop telemetry and a dashboard Loop Optimizer panel.

### Safety
- `BOTTE_LOOP_OPTIMIZER=shadow` is the default; it never changes execution.
- `BOTTE_NEEDLE_ROUTER=0` is the default; no Needle runtime or weights are
  required for Botte Secrète.
- Learned policy and production rollout remain blocked until real, verified
  trajectory and staged-rollout thresholds are met.

## v1.8.0 (2026-07-07) — Belt Wiring & Audit Fixes

### Fixed — cost/logic bugs found via full-repo audit
- `tiered_router.estimate_cost`: clamped input/output tokens to the tier's
  nominal ceiling before billing, under-counting cost for any call bigger
  than that ceiling (verified: -47% on a 20k/10k PREMIUM call). Affected both
  pre-call estimates and `Budget.spend`/`record()`'s actual tracking.
- `universal_compressor.compress`: some strategies could net-expand short
  inputs (a real prompt went 321→325 bytes). Added a passthrough safety net.
- `fallow_like` CLI `health` command: `calculate_health(result)` was called
  without any analyzer results, so the score was always 100/A regardless of
  real findings (verified: 319 findings, still 100/A → 48/D after the fix).
- `security_scanner audit` subcommand crashed on every call (missing
  `--verbose`/`--format` registration on that subparser).
- `botte_proxy`: model pricing matched by substring in dict-insertion order —
  `claude-opus` matched `claude` (Sonnet pricing, 5x under) and `gpt-4.5`
  matched `gpt` (30x under). Now matches the longest key first.
- Three README-cited scripts crashed on Windows consoles (missing UTF-8
  setup): `scripts/benchmark_full.py`, `scripts/test_mcp_gateway.py`,
  `skills/auto_router/checkup_belt2.py`. The first two also had a hardcoded
  `python3` and (for `test_mcp_gateway.py`) a `subprocess` `env=` that
  replaced the whole environment instead of extending it.
- `scripts/test_readme_commands.py` executed ` ```python ` fenced snippets as
  shell commands (guaranteed failures) — now only ` ```bash ` fences run.
- `skills/fleet/status.py` read its own registry, silently diverging from the
  one `dashboard fleet add` writes; now a view over the single source of truth.

### Added — Belt 2.0 wired into the router
- `auto_router.decide()` consults Belt 2.0's `cloud_escalation_predictor` when
  Belt 1.0 abstains (local-pull only, same conservative window); exposed in
  `explain()` under `trace['belt2']`.
- Fixed the binary-abstention floor: a 2-class softmax's max is always ≥ 0.5,
  so the belt could never abstain at threshold 0.50 — binaries now use 0.66.
- MCP server: `bench_run`/`doctor`/`fleet_status` were declared but had no
  dispatch handler (silent failure on call) — now wired. New tools `compress`,
  `shape_query`, `belt2_hint` expose modules that existed since v1.7.0 but
  were unreachable from the harness.

691/691 tests (+2 regression tests: compressor never-expands, cost_estimator
actual-tokens billing). Self-audit: 89/100 (B), up from a stale 75/100 badge.

## v1.7.0 (2026-07-06) — Copilot Analysis Edition

### 🚀 Infrastructure Proxy (5 features)
- **Proxy mode**: `python -m skills.botte_proxy.cli proxy --port 8787`
- **Agent wrap**: `python -m skills.botte_wrap.cli wrap claude|codex|aider|opencode`
- **Output reduction**: verbosity steering + response content trimming
- **CacheAligner**: normalized prefixes for provider KV caches
- **Dollar savings**: MODEL_PRICES pour 20+ providers, dashboard $$$

### Added
- **Lazy MCP tool loading** (`skills/llm_mcp/lazy.py`) — the biggest single amont
  cut `context_profiler` identified: `tools/list` now returns only a small core
  (`local_chat`, `auto_route`, `find_skills`, `conduct`) + a `find_tool(query)`
  meta-tool instead of injecting all ~39 tools' full JSON Schema on every turn —
  the same pattern this harness itself uses (ToolSearch). `find_tool` is a 0-token
  lexical search over name+description; a strong match returns the full schema in
  one round trip. `tools/call` still dispatches any tool by name regardless of
  listing — lazy loading only shrinks the catalog, not what's callable. Toggle
  with `BOTTE_MCP_LAZY_TOOLS=0`. **Measured saving: ~3.3k tokens (84% of the
  tool-schema cost)** — `context_profiler` now reports the real lazy-mode number
  instead of an estimate.
- **`context_profiler`** (`skills/context_profiler/`) — measures a project's
  always-on prefix (agent directives + core rules + **MCP tool schemas** + skill
  catalogue) in tokens and as a % of small local windows (64k/128k/256k), with a
  reduction plan (lazy tool loading, on-demand skill search). Serves the "let modest
  machines run local LLMs usably" axis: on this repo the prefix is ~7.9k tok (12% of
  a 64k window) and shrinks to ~1.4k tok (2%) once tools are lazy-loaded and skills
  fetched on demand. New CLI + `context_profile` MCP tool. 0 cloud tokens.
### 📊 Pipeline optimizations (P41-P47)
- **Prefix pruner**: removes unused context sections
- **Agent cache**: skips agents when output is predictable (hash/fingerprint/fuzzy)
- **Token shaper**: 4 niveaux de compression adaptative (aggressive→none)
- **Self-budget**: agents manage their own token budgets
- **Context slicer**: segmentation multi-window du contexte
- **Token compressor**: semantic hashing + byte-pair pruning
- **Auto-distill**: distillation cloud → micro-NN (logistic regression pure numpy)

### 🧠 Micro-NN Belt 2.0 (7 new models)
- compressibility_predictor (6f→3c): optimal compression level
- context_pruning_predictor (6f→2c): section to keep or remove
- skip_agent_predictor (7f→2c): execute or skip
- cloud_escalation_predictor (7f→3c): local small/big/cloud
- response_length_predictor (6f→3c): response length
- tool_call_predictor (7f→2c): LLM seul ou avec outils
- semantic_cache_hit_predictor (7f→2c): cache hit ou miss
- **Total**: 11 operational micro-NNs ✅

### 🔄 Cheap retroactive loops (P48-P55)
- **Context windows**: independent windows + deltas between steps
- **Prefix tree**: prefix trie + prompt diffing between agents
- **Harness delta**: differential verification (changed sections only)
- Loop budgeter, router, cache, and compression (integrated above)

### 🧩 DAG/RAG optimizations (P56-P62)
- **DAG waves**: synchronous wave execution (topological sort)
- **DAG pruning**: removal of unnecessary nodes and branches (BFS)
- **DAG memoization**: cache par nœud (input hash → output)
- **RAG delta retrieval**: documents nouveaux uniquement
- **RAG query shaping**: concise reformulation (removes filler)
- **RAG-guided routing**: RAG → meilleur agent (keyword scoring)

### 🚀 Advanced Ideas (P63-P69)
- **A2AC**: compressed binary inter-agent format (1024-entry dictionary, 4-bit quantization)
- **Loop Distillation**: distill successful retroactive loops
- **Skill-Level RAG**: load only skills needed for a task
- **Predictive Fix Planning**: predict fix cost and utility
- **Agent Memory Compression**: cluster and deduplicate agent memories
- **Predictive Routing**: select the best agent path before execution
- **Agent Knowledge Distillation**: transfer knowledge between agents

### 🧪 Benchmark
- `scripts/benchmark_full.py`: mesure les 14 modules
- Result: **81.5% compression** on real samples
- Logs: 90.2% | JSON: 92.4% | Code: 5.2% | Contexte mixte: 55.4%

### 📈 Stats
- Skills: 57 → **~90**
- Micro-NN: 4 → **11**
- New modules: **35** (P41-P69)
- Commits cette session: **22**
- Measured savings: **590M tokens/month** (May 2026)

### 🔧 Autre
- CogniARC: adaptive exploration, PuzzleStrategy, generic hypotheses
- Kanboard-Neo: real dashboard metrics, Linear-style activity feed
- arc-human-skills: 2 747 lignes drawing improvements
- Hermes provider `botte-proxy`: ready to use
