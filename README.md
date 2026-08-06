# 🧦 Botte Secrète — Multi-Agent Token Optimization Platform

[![CI](https://github.com/zedarvates/botte-secrete/actions/workflows/ci.yml/badge.svg)](https://github.com/zedarvates/botte-secrete/actions)
[![Tests](https://img.shields.io/badge/tests-local%20validation-brightgreen)](https://github.com/zedarvates/botte-secrete)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/zedarvates/botte-secrete/blob/main/LICENSE)
[![Release](https://img.shields.io/badge/release-v1.9.0-blue)](https://github.com/zedarvates/botte-secrete/releases)
[![Token Savings](https://img.shields.io/badge/token%20savings-81%25-blue)](https://github.com/zedarvates/botte-secrete)
[![Self-Audit](https://img.shields.io/badge/self--audit-89%2F100%20(B)-green)](https://github.com/zedarvates/botte-secrete)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![GPG Signed](https://img.shields.io/badge/commits-GPG%20signed-green)](https://github.com/zedarvates/botte-secrete)

> *"Tous pour un, un pour tous."* — Les Trois Mousquetaires

A multi-agent pipeline for code audit, automated fixes, token optimization,
and adversarial red teaming — all built to run efficiently on local hardware.

**The goal: make your projects cheaper to work on.** Deploy it into any repo and
its agent routes cheap work to local models (LM Studio / Ollama) for **0 cloud
tokens**, escalates only the hard parts to the cloud, picks tools locally, and
tells you what hardware/infra changes would cut cost further.

### Quick Facts

| Metric | Value |
|--------|-------|
| Tests | Run `python scripts/run_tests.py` locally for the current complete result |
| Skills | **~90** (code audit, fix, routing, MCP, NLP, solvers, security, docs, compression, memory, proxy, distill, belt 2.0) |
| Micro-NN | **11 models** (4 originals + 7 Belt 2.0) — grounding tracked by `nn_audit`, wired into `auto_router` |
| Token savings | **81.5%** (benchmark: logs 90%, JSON 92%, code 5%, context 55%) |
| Self-audit | **89/100 (B)** — `python -m skills.mousquetaires.scripts.porthos_audit . <out_dir>` |
| Dependencies | `numpy`, `pydantic`, `tree-sitter` — see [`requirements.txt`](requirements.txt) |
| License | **MIT** — free forever |
| Install | `pip install git+https://github.com/zedarvates/botte-secrete` → `botte` + `botte-mcp` commands |
| Deploy | One command: `botte bootstrap /your-project` |

## 🔁 Loop Optimizer — shadow-safe retroactive loops

The Loop Optimizer stops repeated failures before they spend a second budget,
reuses exact cache entries and limits intermediate context to the active delta.
It is **shadow-only by default**: it records a proposed decision locally and
does not alter execution. Its optional Needle tool router has no mandatory
dependency and remains disabled until a local benchmark clears strict safety
and latency thresholds.

```bash
python -m skills.loop_optimizer.cli explain demo-loop "verify targeted tests" --tools run_tests
python -m skills.dashboard.cli . --tui
```

See [the Loop Optimizer guide](docs/loop-optimizer.md) for modes, MCP tools,
benchmark gates and the progressive rollout policy.

## 🩹 v1.8.0 — Belt Wiring & Audit Fixes (July 2026)

A correctness pass over v1.7.0: Belt 2.0 was trained but never consulted, several
CLIs crashed on real invocations, and one cost formula silently under-billed.

### Belt 2.0 is now live
`auto_router.decide()` consults `cloud_escalation_predictor` whenever Belt 1.0
abstains (same conservative window: borderline tier, local-pull only, never
escalates) — the 7 trained predictors were previously reachable only from a
benchmark script. Visible in `explain()`'s trace under `belt2`. Also fixed the
binary-abstention floor: a 2-class softmax's max is always ≥ 0.5, so the old
0.50 threshold could never abstain — binaries now use a 0.66 floor.

### MCP server: 3 broken tools fixed, 3 new ones wired
`bench_run`/`doctor`/`fleet_status` were declared in `tools/list` but had no
dispatch handler (silent 404 on call). New: `compress` (universal_compressor),
`shape_query` (token_shaper), `belt2_hint` (the 7 Belt 2.0 predictors) — modules
that existed since v1.7.0 but were unreachable from the harness.

### Real bugs found and fixed via a full-repo audit
- **Cost under-billing**: `tiered_router.estimate_cost` clamped both token
  counts to the tier's nominal ceiling before billing — a 20k-in/10k-out
  PREMIUM call was billed as 8k/8k (47% under). Fed both pre-call estimates
  and the actual budget tracker (`Budget.spend`).
- **Compression that expands**: some `universal_compressor` strategies could
  net-*grow* short inputs (321→325 bytes on a real prompt). Added a
  passthrough safety net — never return more than came in.
- **Fake health score**: the `fallow_like health` CLI command always reported
  100/A regardless of real findings (a wiring bug — analyzer results were
  never passed to the scorer). Now reflects them (48/D on a real run).
- **`security_scanner audit` crashed on every invocation** (missing arg
  registration); `botte-proxy` mispriced Claude Opus/GPT-4.5 (substring match
  picked the wrong price tier — up to 30x under).
- Three README-cited scripts crashed on Windows consoles (`benchmark_full.py`,
  `test_mcp_gateway.py`, `checkup_belt2.py`) from missing UTF-8 setup, plus a
  hardcoded `python3` and an environment-clobbering `subprocess` call.

`skills/dashboard/fleet.py` and `skills/fleet/status.py` used to read two
different, silently-diverging registries — `fleet/status.py` is now a thin
view over the one true registry.

691/691 tests (+2 new regression tests for the cost and compression fixes).

## 🚀 v1.7.0 — Copilot Analysis Edition (July 2026)

**35 new modules** from the Copilot source review, raising measured savings from **65% to 81.5%**.

### Pipeline optimizations (P41-P47)
| Module | Fonction | Gain |
|--------|----------|:----:|
| **Prefix Pruner** | Removes unused context sections | +5-10% |
| **Agent Cache** | Skips agents when output is predictable | +10-15% |
| **Token Shaper** | Compression adaptative per-turn (4 niveaux) | +10-15% |
| **Self-Budget** | Agents manage their own token budgets | +5-10% |
| **Context Slicer** | Segmentation multi-window | +5-8% |
| **Token Compressor** | Semantic hashing + byte-pair pruning | +5-12% |
| **Auto-Distill** | Distillation cloud → micro-NN | +10-20% |

### Micro-NN Belt 2.0 (7 nouveaux)
`compressibility`, `context_pruning`, `skip_agent`, `cloud_escalation`, `response_length`, `tool_call`, `semantic_cache` — 11 micro-NN au total.

### Cheap retroactive loops (P48-P55)
Context Windows, Prefix Tree, and Harness Delta reduce loop costs by 40-70%.

### DAG/RAG optimizations (P56-P62)
DAG Waves, Pruning, Memoization — RAG Delta Retrieval, Query Shaping, guided Routing.

### Advanced (P63-P75)
A2AC (Agent-to-Agent Compression), Loop Distillation, Skill-Level RAG, Predictive Fix Planning, Agent Memory Compression, Predictive Routing, Agent Knowledge Distillation, Pipeline Integrator, Health Monitor, Meta-Optimizer.

### 🧪 Benchmark
```bash
python scripts/benchmark_full.py
# → 81.5% compression | Logs: 90.2% | JSON: 92.4% | Context: 55.4%
```

### 🧠 11 operational micro-NNs
```bash
python -m skills.auto_router.checkup_belt2
# → 11/11 models: ✅ ALL OPERATIONAL
```

## ✨ Fable6 — New in v1.6.0

7 new skills from the Fable6 R&D phase (Headroom, Ponytail, Stanford AutoMem):

### 🗜️ Universal Compressor (`skills/universal_compressor/`)
Multi-type content compression before it reaches the LLM. Auto-detects type, applies best strategy, reversible (CCR-like).

```bash
python -m skills.universal_compressor.cli compress file.log --type log
python -m skills.universal_compressor.mcp_server       # MCP mode
```

| Type | Strategy | Savings |
|------|----------|---------|
| `text` | Dedup lines, collapse blanks | 0-30% |
| `json` | Compact + truncate arrays | 20-60% |
| `log` | Pattern dedup + sampling | 80-98% |
| `tool_output` | Head+tail, strip ANSI | 50-90% |
| `code` | Strip comments, collapse imports | 20-40% |

### 🪜 Decision Ladder (`skills/decision_ladder/`)
Ponytail-inspired YAGNI enforcement. Before writing code, climb 4 rungs:

```python
from skills.decision_ladder.ladder import climb
result = climb("parse JSON config")  # → rung="stdlib", saved_lines=15
```

`stdlib` → `regex_oneliner` → `existing_module` → `new_code`

### 💾 AutoMemory (`skills/auto_memory/`)
Memory as a learnable skill (Stanford AutoMem). Store, recall, compress, and consolidate agent memories.

```python
from skills.auto_memory import init_memory, store_memory, recall_memory
bank = init_memory()
store_memory("user_pref.format", "concise", category="user_pref")
```

Tracks: memory bank, trajectory recorder, pattern extraction, bottleneck compression.

### 📊 Dashboard (`skills/dashboard/`)
Live metrics visualization for all botte-secrete skills.

```bash
python -m skills.dashboard.api        # Start on http://localhost:8765
open http://localhost:8765            # View dashboard
```

Shows: test counts, lines saved, avoidable %, memory stats, compression ratios.

### 🔗 Hermes Bridge (`skills/hermes_bridge/`)
MCP gateway connecting Hermes Agent to botte-secrete tools.

```bash
python -m skills.hermes_bridge.mcp_server  # MCP stdio server
```

Exposes 4 tools: `decision_ladder`, `compress_content`, `memory_stats`, `dashboard_stats`.

### 🧭 Micro-NN Router (`skills/nn_router/`)
4-tier task routing by complexity: nano (rules) → micro (0.5B) → medium (4B) → macro (API).

```python
from skills.nn_router.router import route
tier, model, score = route("audit code quality")  # → ("medium", "gemma-4-e2b", 4)
```

### 🔒 Security Scanner (`skills/security_scanner/`)
Lightweight vulnerability detection: credential leaks, shell injection, path traversal.

```python
from skills.security_scanner.scanner import scan
issues = scan_file("config.py")
# → {"total": 2, "by_severity": {"critical": 1, "high": 0, ...}}
```

## What It Does

1. **Audit** — Static analysis (dead code, duplication, complexity, secrets, boundaries)
2. **Fix** — Automated corrections with verification
3. **Optimize** — Per-project skill filtering, token reduction
4. **Red Team** — Adversarial agents that challenge the Blue Team
5. **Route local↔cloud** — Auto effort estimate sends cheap tasks to local LLMs,
   hard ones to the cloud (DeepSeek/GLM/Nemotron/Grok/Gemma); fusion makes them collaborate
6. **Deploy** — One command wires the whole stack into any project via MCP

## 🧠 The 4-filter stack — why it's cheap

Every task passes through four filters, **cheapest first**. Each filter that handles a
task saves the cost of every filter above it — so most work never reaches the cloud.

| Filter | What runs | Cost | Modules |
|--------|-----------|------|---------|
| **1 · Micro-NN** | tiny trained nets decide routing / classification in ~0 ms | **0 tokens** | `botte_nn` (binary_router, effort_classifier, …) + `features` |
| **2 · Deterministic** | rules, gazetteers, exact solvers — no model at all | **0 tokens** | `nlp_deterministic`, `solvers`, `context_budget` |
| **3 · Local LLM** | small local models (LM Studio / Ollama), wrapped in an anti-hallucination harness | **0 cloud tokens** | `llm_backends`, `local_harness` |
| **4 · Cloud LLM** | only genuinely hard reasoning escalates, cheapest capable model | paid | `auto_router`, `fusion` |

The **NN belt** (`auto_router` + `botte_nn`) decides which filter a task needs; the
**harness** keeps the local model honest (structured output + deterministic verification —
*escalate, don't hallucinate*); the **active-learning loop** sharpens the belt from
explicitly verified outcomes. Executed `auto_route` calls return a `feedback_id`;
`route_feedback` labels it only after a real local/cloud verdict. Trivial work stays local
at 0 tokens; the expensive model is spent only where it
earns its keep.

## 🎬 See it decide, live

Don't take the filter table on faith — watch it work. No LLM, no network, no
setup required:

```bash
python -m skills.demo.cli scripted
```

```
┌─ ROUTING ────────────────────────┐  ┌─ SAVINGS (session) ──────────────┐
│ CLOUD  design a distributed co...│  │ tokens saved          1210       │
│ LOCAL  is this diff a bugfix o...│  │ cloud calls made         1       │
│ LOCAL  rename variable "a" to ...│  │ cloud calls saved        2       │
└──────────────────────────────────┘  │ cache hits               1       │
                                       └──────────────────────────────────┘

┌─ MICRO-NN ───────────────────────┐  ┌─ ESCALATIONS ────────────────────┐
│ anomaly_detector   [0.04|0.96]...│  │ local → cloud  verification_fa...│
│ effort_classifier  conf=0.93     │  └──────────────────────────────────┘
└──────────────────────────────────┘
```

That's the built-in scripted scenario — 6 fixed steps touching every filter
(micro-NN routing, a deterministic classifier, a cache hit, a cloud
escalation, a verification-failure escalation, an anomaly-detector output).
Once deployed into a real project, `python -m skills.demo.cli live .` shows
the same panels fed by genuine decisions while an agent works, and
`python -m skills.dashboard.cli . --tui` / `--watch` gives the metrics/cost
counterpart. Don't trust the "~65%" savings number either — run
`python -m skills.bench.cli` for a reproducible, checkable measurement.
Full checkup + machine scan + ranked opportunities in one command:
`python -m skills.checkup.cli . --doctor`. See
[skills/demo](skills/demo/SKILL.md), [skills/dashboard](skills/dashboard/SKILL.md),
[skills/bench](skills/bench/SKILL.md), [skills/checkup](skills/checkup/SKILL.md).

## ⚡ Install & deploy into your project

**Option A — pip install (no clone needed):**

```bash
pip install git+https://github.com/zedarvates/botte-secrete
botte --help          # doctor · route · dashboard · bootstrap · mcp · belt
botte belt            # verify the 11 micro-NN ship with the package
botte bootstrap /path/to/your-project
```

The install also provides `botte-mcp` — point your agent's `.mcp.json` at it
directly instead of a repo checkout.

**Option B — from a clone:**

```bash
python -m skills.bootstrap.cli /path/to/your-project   # wire MCP tools, audit directives, write .botte config
python -m skills.infra_advisor.cli auto .              # one-pass cost audit (directives + infra + duplication)
python -m skills.llm_backends.cli audit --fresh        # what local models can this machine run?
```

After deploy, restart your agent in the project — it gains the `botte-llm` MCP
tools: `auto_route`, `local_chat`, `fusion`, `find_skills`, `infra_tips`,
`auto_audit`, `audit_local_usage`, and more.

## 🔒 System Impact

Before running anything, here's exactly what Botte Secrète changes on your machine:

| Item | Change |
|------|--------|
| `.mcp.json` | Adds 5+ MCP tools (auto_route, local_chat, fusion, find_skills, infra_tips) |
| `.botte-cache/` | Created at project root — caches scan results between runs |
| `.botte/events.jsonl` | Created at project root, opt-in via use — local decision log for `demo`/`dashboard`/`statusline`, rotates at 5 MB, never leaves the machine |
| `.skills-profile` | Per-project skill selection — reduces context tokens |
| `~/.botte/fleet.json` | **Only if you run `dashboard fleet add`** — an explicit, opt-in registry of project paths for the multi-project `--fleet` view. Nothing is scanned or registered automatically |
| Network | **None by default.** Only connects to local LLM servers (localhost:1234, etc.) |
| System services | **None.** No cron, no daemon, no sudo, no startup entries |
| Dependencies | `numpy` + `pydantic` / `tree-sitter` for the analyzers (`requirements.txt`). No heavy ML frameworks |
| Telemetry | **None.** No analytics, no tracking, no phone-home |

**Verify for yourself:** the entire test suite runs offline:
```bash
python scripts/run_tests.py   # complete offline test suite, 0 cloud calls
python -m pytest --rootdir=. -q     # 77 Fable6 tests (0 cloud calls)
```

## ✅ Smoke Test

Clone, verify, and run in under 60 seconds:

```bash
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete
python scripts/run_tests.py                    # complete offline test suite
python -m pytest --rootdir=.                   # 77 Fable6 tests
python -m skills.llm_backends.cli scan         # detect local LLMs
python -m skills.auto_router.cli route "hello" # 0-token routing decision
```

## 📋 Copy-paste prompts

**No setup knowledge needed** — paste this into your favourite LLM's project chat
(Claude, ChatGPT, Cursor, …). It will install and wire everything for you:

```text
Set up "Botte Secrète" to cut my AI token/cost on THIS project. Work step by
step, run the commands, and stop to ask me only if something fails.

1. Get the toolkit (skip if the folder already exists):
   git clone https://github.com/zedarvates/botte-secrete
2. From inside the botte-secrete folder, deploy it into MY project:
   python -m skills.bootstrap.cli "<ABSOLUTE PATH TO MY PROJECT>"
   (this only ADDS to my .mcp.json — it never deletes my existing setup)
3. Tell me what local models I can run:
   python -m skills.llm_backends.cli audit --fresh
4. Show me my cost report (per component + tokens/session):
   python -m skills.metrics.cli "<ABSOLUTE PATH TO MY PROJECT>"
5. Restart yourself in my project so you pick up the new MCP tools, then from
   now on route cheap work — classification, extraction, summaries, and choosing
   which skills/tools to use — to my LOCAL model (tools: local_chat, auto_route,
   find_skills). Keep the expensive cloud model only for hard reasoning, and
   prefer `rtk <command>` for terminal commands.

Finish by telling me the headline: how many tokens per session this saves.
```

**Run the tests** — paste into a terminal at the repo root (one command, works on
Windows/macOS/Linux):

```text
python scripts/run_tests.py
```

(or ask your agent: *"Run the Botte Secrète test suite and report any failures:
`python scripts/run_tests.py`"*)

## ⚔️ Architecture

```
                    👑 Athos (Orchestrator)
                    ┌─────────┼─────────┐
                    │         │         │
              🥊 Porthos   📿 Aramis   ⚔️ d'Artagnan
              (Audit) ∥   (Optimize)   (Fix)
                    └─────────┼─────────┘
                              │
                    👑 Le Cardinal (Red Team)
                    ┌─────────┼─────────┐
                    │         │         │
              🗡️ Rochefort  🔪 Milady  🕯️ Cte Wardes
           (Counter-Audit) (Counter-Fix)(Counter-Optimize)
```

Blue Team: **Porthos ∥ Aramis → d'Artagnan → Athos** (parallel audit+optimize)
Red Team: **Rochefort ∥ Milady ∥ Cte Wardes → Le Cardinal** (parallel counter-attacks)

## 📦 Modules

| Module | Purpose | Impact |
|--------|---------|--------|
| `core-agent.md` | Shared rules: botte, anti-patterns, clarification, budgets | -57% pre-prompts |
| `mousquetaires/` | Blue Team — 4 agents (audit, fix, optimize, orchestrate) | Automated pipeline |
| `cardinal/` | Red Team — 4 adversarial agents (counter-audit, counter-fix, counter-optimize) | Quality gate |
| `clarification/` | Proactive questions — max 5, silence=auto | -80% wasted work |
| `cache/` | `.botte-cache/` — avoid re-scanning between agents | -50% re-scan tokens |
| `llm_backends/` | **P15** — Discover/audit/call local LLM servers (LM Studio, Ollama, …) | Offload → 0 cloud tokens |
| `llm_mcp/` | **P15** — MCP server exposing local-LLM tools to agents | Auto local routing |
| `local_router/` | **P9** — Routes tasks to local models (Hailo/ComfyUI/LocalAI) | -40% cloud tokens |
| `media_loader/` | **P10** — Extracts text from media before LLM sees it | -95% media tasks |
| `response_cache/` | **P8** — Semantic response cache (hash + similarity) | -60% repeated queries |
| `vector_protocol/` | **P11** — Agents communicate via quantized vectors | -70% inter-agent |
| `ultra_compact/` | **P12** — Single-char keys, array format, delta-only | -90% iterative |
| `code_fingerprint/` | **P13** — Hash functions, skip unchanged code | -80% re-analysis |
| `tiered_router/` | **P14** — 5-level model selection + agent compression | -95% vs all-PREMIUM |
| `auto_router/` | **P17** — Auto local↔cloud routing (DeepSeek/GLM/Nemotron/Grok/Gemma) + fusion | Effort-based, budget-aware |
| `loader/` | Pre-prompt loader for `delegate_task` | Correct agent context |
| `fallow_like/` | **P35** — 9 static analyzers (dead code, dup, complexity, secrets, **taint/data-flow security**, boundaries, etc.) | Code quality + security |
| `skill_project_optimizer/` | Per-project skill filtering, token profiling | -73% skill tokens |
| `directives_audit/` | **P16** — Audit agent-guidance files (CLAUDE.md/AGENTS.md/specs, md+html) | Avoid blind agent runs |
| `skill_finder/` | **P18** — Find relevant skills/tools for a task locally (0 cloud tokens) | -100% selection cost |
| `bootstrap/` | **P19** — Deploy the whole stack into a project (one command) | Makes it real |
| `capabilities/` | **P26** — Self-model: capability registry + curator + ASCII system tree | Collection → system |
| `cluster/` | **P27** — Homelab as one schedulable resource — spread work to idle machines | Recover idle capacity |
| `conductor/` | **P28/P32** — Route a goal → ordered local-first plan, and execute its safe steps | Generalised router + executor |
| `control_loop/` | **P29** — Measure routing outcomes → adapt thresholds (self-improving) | The router that learns |
| `report/` | **P30** — Save any audit as a timestamped .md/.html, browsable any time | Consultable audits |
| `cost_estimator/` | **P31** — Estimate tokens·model·money·time for a task or a fix | Know cost upfront |
| `fix/` | **P31** — List correctable issues, each with a cost estimate (plan-only) | Cost of corrections |
| `trends/` | **P31** — Track audit metrics over time + delta | See progress |
| `metrics/` | **P22** — Cost-focused metrics per component (LOC, always-on cost, savings) | Quantify the win |
| `preflight/` | **P23** — Committed policy + per-turn hook (prefer-local, auto) | Enforce, not opt-in |
| `checkup/` | **P23** — Canonical one-command project checkup + drift detection | No hand-written prompt |
| `docs_steward/` | **P36** — Scoped docs map for multi-component projects + docs lifecycle (prune finished tasks, archive reports) | Cut always-on doc tokens |
| `context_budget/` | **P37** — Optimal skill/doc set to load under a token budget (exact 0/1 knapsack, OR-Tools-style) | Cut always-on context |
| `nlp_deterministic/` | **P38** — Classify/extract without an LLM (rules + gazetteers + local embedding) | 0-token triage/routing |
| `solvers/` | **P39** — Deterministic assignment / bin-packing / precedence scheduling (OR-Tools-style, stdlib) | 0-token structured decisions |
| `cwe_kb/` | **P40** — Local CWE knowledge base (RAG) — enrich/de-noise security findings with name, description, mitigation | Explain & prioritise findings |
| `botte_nn/` | **Micro-NN belt** — 6 tiny trained *classifiers* (feedforward nets, Rust + numpy fallback — not LLMs) decide routing/classification in ~0 ms; self-improving via an active-learning loop | Trivial decisions → 0 cloud tokens |
| `botte_nn/features` | **Featurizer** — documented, range-validated feature schema for every micro-NN (`featurize`/`classify`); turns raw input into the exact vector each model expects | No silent garbage-in |
| `local_harness/` | **Anti-hallucination harness** — structured output + deterministic verification (schema / evidence-in-context / citations-exist / code-parses); abstain & escalate rather than invent | Trust small local models |
| `infra_advisor/` | **P20** — Hardware/software/MCP cluster tips + auto audit (ASCII diagram) | Cut cost beyond code |
| `prompt_improver/` | **P21** — Rewrite rough prompts into pro structured/JSON prompts locally | 0-token prompt eng. |
| `ingest/` | **P24/P33** — Local web scraping + Qdrant ingestion with real local embeddings (auto-resolved, hash fallback) | 0-token extraction |
| `docgen/` | **P24** — Docs: local draft → cloud refine + local session review | Verbose docs, local |
| `app_test/` | **P25** — Local-first GUI testing (OculiX image-match) + HTML post-mortem (logs/screenshots) | 0 cloud vision |
| `botte` | Terminal wrapper — compresses command output | -60-99% terminal tokens |
| `code-rules/` | Coding standards: stdlib-first, flat architecture | -30% context |
| `simplify-code/` | Parallel 3-agent code review | -25% post-edit tokens |
| `understand-anything/` | Codebase knowledge graph | -50% exploration |

## 🚀 Quick Start

```bash
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete

# Full Blue Team pipeline
python3 -m skills.mousquetaires.cli run ~/your-project --output ./reports

# Blue + Red Team (adversarial)
python3 -m skills.mousquetaires.cli run ~/your-project --output ./blue
python3 -m skills.cardinal.cli run ~/your-project --blue-reports ./blue --output ./red
python3 -m skills.cardinal.cli confront --blue ./blue --red ./red

# Token optimization only
python3 -m skills.skill_project_optimizer.cli optimize ~/your-project

# Code audit only
python3 skills/mousquetaires/scripts/porthos_audit.py ~/your-project ./audit-output

# View token savings
botte gain
```

## 💰 Token Savings

| Technique | Savings | How |
|-----------|---------|-----|
| Shared Core Prompt | 57% | DRY: core loaded once, 8 deltas vs 8 full copies |
| JSON Output Formats | 75-80% | Compact schemas vs verbose markdown |
| Project Cache | 50% | `.botte-cache/` avoids re-scanning |
| Per-Project Skill Filtering | 73% | `.skills-profile` excludes irrelevant skills |
| botte Terminal Wrapper | 60-99% | Compressed command output |
| Token Budget Enforcer | Qual. | Hard limits per agent (800-2500 tok) |
| **Combined** | **~65%** | **Pipeline-wide reduction** |

## 🎯 Token Budgets

| Agent | Budget | Strategy if exceeded |
|-------|--------|---------------------|
| Porthos | 2000 tok | Truncate findings >10 |
| d'Artagnan | 1500 tok | Report skipped fixes |
| Aramis | 2500 tok | P0 actions only |
| Athos | 1000 tok | Synthesis + links |
| Rochefort | 1500 tok | Top 5 false negatives |
| Milady | 1200 tok | Top 5 regressions |
| Cte Wardes | 1200 tok | Top 5 over-optimizations |
| Le Cardinal | 800 tok | Verdict + top 3 actions |

## 🛠️ botte — Token-Optimized Terminal

```bash
botte cargo build       # -80%
botte cargo test        # -90%
botte git status        # -59%
botte git diff          # -80%
botte pnpm install      # -90%
botte docker ps         # -85%
botte gain              # View savings
botte discover          # Find missed optimization opportunities
```

## 📂 Project Structure

```
botte-secrete/
├── skills/
│   ├── core-agent.md              # Shared rules (loaded once for all agents)
│   ├── cache/                     # .botte-cache/ system
│   ├── clarification/             # Proactive question engine
│   ├── loader/                    # Pre-prompt loader for delegate_task
│   ├── fallow_like/               # 9 static analyzers (incl. taint/data-flow security)
│   ├── skill_project_optimizer/   # Per-project token optimizer
│   ├── mousquetaires/             # Blue Team (4 agents)
│   │   ├── prompts/               # Agent pre-prompts (deltas)
│   │   ├── scripts/               # Agent execution scripts
│   │   ├── templates/             # Report templates
│   │   └── cli.py                 # CLI (typer + rich)
│   └── cardinal/                  # Red Team (4 agents)
│       ├── prompts/               # Adversarial pre-prompts
│       └── scripts/               # Confrontation scripts
├── docs/
│   ├── plans/                     # Architecture design docs
│   └── schemas/                   # JSON report schemas
├── scripts/
│   └── botte                      # Token-optimized terminal wrapper
└── README.md
```

## 🏠 Local LLM Backends (P15)

Detect and use local model servers so cheap tasks never hit the cloud. Works
with **LM Studio, Ollama, LocalAI, vLLM, llama.cpp, Jan, KoboldCpp** — anything
speaking the OpenAI `/v1` schema.

```bash
# Discover what's reachable (localhost, a host, or sweep the /24)
python -m skills.llm_backends.cli scan
python -m skills.llm_backends.cli scan --subnet
python -m skills.llm_backends.cli scan 192.168.1.47

# Audit: do you use local models? what can this machine run? next steps?
python -m skills.llm_backends.cli audit --fresh

# Run a prompt locally — 0 cloud tokens
python -m skills.llm_backends.cli chat "classify: bug or feature?" --max-tokens 128
```

The audit profiles your hardware (RAM/VRAM/GPU) and, if you have **no** local
model yet, gives step-by-step setup tuned to what your machine can actually run.

### Wire it into Claude Code (MCP)

Copy `configs/mcp.example.json` to `.mcp.json`, set `cwd` to this repo, and the
agent gains five tools: `discover_backends`, `list_models`, `audit_local_usage`,
`route_task`, `local_chat`. Tell it *"classify these locally"* and it offloads
to your GPU. See [`skills/llm_mcp/SKILL.md`](skills/llm_mcp/SKILL.md).

## 🧭 Auto Router + Fusion (P17)

Decides **local vs cloud automatically** from an effort estimate, across local
backends *and* cloud providers (DeepSeek, Zhipu GLM, NVIDIA Nemotron, xAI Grok,
Google Gemma — all OpenAI-compatible).

```bash
python -m skills.auto_router.cli route "classify: bug or feature?"      # → LOCAL
python -m skills.auto_router.cli route "design a distributed cache, prove correctness"  # → cloud tier
python -m skills.auto_router.cli providers                              # catalog + availability
python -m skills.auto_router.cli run "summarize this in 2 lines"        # decide + execute
```

Trivial tasks stay local (0 cloud tokens); hard ones pick the cheapest capable
cloud model — budget-aware, and falling back to local when no cloud key is set.
Cloud access via `OPENROUTER_API_KEY` (all models) or native keys
(`DEEPSEEK_API_KEY`, `XAI_API_KEY`, `ZHIPUAI_API_KEY`, `NVIDIA_API_KEY`).

**Fusion** makes models collaborate:

```bash
python -m skills.auto_router.cli fusion cascade "is 17 prime?"           # cheap→escalate if unsure
python -m skills.auto_router.cli fusion draft   "explain the CAP theorem" # local drafts, cloud refines
python -m skills.auto_router.cli fusion vote    "capital of France, one word?"  # consensus
```

Also exposed as MCP tools (`auto_route`, `fusion`). See
[`skills/auto_router/SKILL.md`](skills/auto_router/SKILL.md).

## 🔬 Hardware Acceleration

- **Hailo-8** (EUREKAI 192.168.1.47) — YOLOv8, ResNet-18, PaddleOCR
- **ComfyUI** (EUREKAI :8188) — Local Stable Diffusion
- **Bonsai Image** — WebGPU ternary model
- Zero cloud API costs for vision/generation

## 🗺️ Roadmap

- [x] P0: Shared core + stripped prompts + JSON schemas (-57% prompts)
- [x] P1: Project cache + parallel pipeline + token budgets (-50% re-scans)
- [x] P2: Output truncation + smart pre-fetching
- [x] P3: Pre-prompt loader + agent diff language + consolidated README
- [x] P4: SKILL.md for all modules + unified pipeline script
- [x] P7: Dashboard HTML + ticket generator for coding agents
- [x] P8: Semantic response cache via Qdrant (-60% repeated queries)
- [x] P9: Local model router (Hailo/ComfyUI/LocalAI) (-40% cloud tokens)
- [x] P10: Progressive media loader (-95% media tokens)
- [x] P11: Vector agent protocol (-70% inter-agent tokens)
- [x] P12: Ultra-compact JSON formats (-90% iterative reports)
- [x] P13: Code fingerprinting (-80% re-analysis)
- [x] P5: CI/CD integration (pre-commit hooks, GitHub Actions)
- [x] P6: Real-time dashboard (auto-watch, savings chart, live status)
- [x] P14: Tiered model selection + agent-to-agent compression
- [x] P15: Local LLM backends (LM Studio/Ollama discovery, audit, MCP server)
- [x] P16: Directives audit — validate CLAUDE.md/AGENTS.md/specs across formats (incl. HTML)
- [x] P17: Auto local↔cloud router (effort-based) + multi-provider catalog + fusion (cascade/draft-refine/vote)
- [x] P18: Local skill/tool finder — zero-token retrieval for skill selection
- [x] P19: Project deployer — `botte setup <project>` wires MCP + directives audit + config
- [x] P20: Infra advisor — cluster hardware/software/MCP tips + auto audit (ASCII cluster diagram)
- [x] P21: Prompt improver — local-LLM rewrite to professional structured / JSON prompts (0 cloud tokens)
- [x] P22: Project metrics (per-component LOC, always-on cost, savings) + fallow scanner that scales to large repos
- [x] P23: Enforcement layer — committed policy + preflight hook (auto prefer-local) + canonical /checkup
- [x] P24: Local web scraping + Qdrant ingestion (foundation) + docs draft→refine + session review
- [x] P25: Local-first GUI app testing (OculiX) + HTML post-mortem report; OculiX visual-control MCP server wired by the deployer
- [x] P26: Capability registry + curator + layered system map (the toolkit's self-model)
- [x] P27: Cluster scheduler — discover machines, spread work to idle boxes (LRU), agent delegation hand-off
- [x] P28: Conductor — route a goal to an ordered local-first plan of capabilities (the generalised router)
- [x] P29: Control loop — measure routing outcomes and adapt the effort→tier thresholds (self-improving)
- [x] P30: Report persistence — save audits as timestamped .md/.html (name+date+time), browsable via `report list`
- [x] P31: Cost estimation (tokens·model·money·time) + fix plan with per-correction cost + metric trends
- [x] P32: Conductor executor — run a plan's read-only steps unattended; confirm-gate mutating/cloud steps
- [x] P33: Real local embeddings for ingest — auto-resolve a local /v1/embeddings endpoint (hash fallback)
- [x] P34: GitHub Action — local-first /checkup verdict posted (and updated) as a PR comment, 0 cloud tokens
- [x] P35: Taint / data-flow security analyzer (neuro-symbolic, local-first) — source→sink + CWE tags, `security_scan` MCP tool
- [x] P36: Docs steward — scoped documentation map for multi-component projects + docs lifecycle (prune finished tasks, archive reports); `docs_map`/`docs_lifecycle` MCP tools
- [x] P37: Context budget — exact 0/1 knapsack (OR-Tools-style) picks the optimal skill/doc set to load under a token budget; `context_budget` MCP tool
- [x] P38: Deterministic NLP — classify/extract without an LLM (rules + gazetteers + local embedding); `nlp_classify`/`nlp_extract` MCP tools
- [x] P39: Deterministic solvers — assignment (LPT) / bin-packing (FFD) / precedence scheduling (DAG waves); `schedule_plan`/`assign_work` MCP tools (OR-Tools-inspired)
- [x] P40: Local CWE knowledge base (RAG) — enrich/de-noise security findings (name, description, mitigation) by id or local embedding; `cwe_explain` MCP tool, wired into `security_scan`

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md). Current: **v1.9.0**.

## 📊 Adoption & Key Facts

- **700+** tests across the canonical runner, 0 failures in the clean publication candidate
- **50+** independent skills — audit, fixes, routing, MCP, security, and docs
- **11** micro-NNs — 4 grounded; synthetic models remain decision-gated
- **~65%** token savings across agent workloads
- **0** heavy ML runtime dependencies — stdlib + NumPy only
- **GPG-signed** — every commit can be verified
- **MCP gateway** — 20+ tools exposed, compatible with any agent

## 📜 License

MIT — Use freely, improve constantly.

## 👤 Author

Sylvain Galliez ([@zedarvates](https://github.com/zedarvates))


---

[![Donate](https://img.shields.io/badge/☕%20Soutenir-BTC%20%7C%20ETH-orange)](DONATE.md)
