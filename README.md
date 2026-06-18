# 🧦 Botte Secrète — Multi-Agent Token Optimization Platform

[![CI](https://github.com/zedarvates/botte-secrete/actions/workflows/ci.yml/badge.svg)](https://github.com/zedarvates/botte-secrete/actions)
[![Tests](https://img.shields.io/badge/tests-94%2F94-brightgreen)](https://github.com/zedarvates/botte-secrete)
[![Token Savings](https://img.shields.io/badge/token%20savings-85%25-blue)](https://github.com/zedarvates/botte-secrete)
[![Self-Audit](https://img.shields.io/badge/self--audit-59%2F100%20(C)-orange)](https://github.com/zedarvates/botte-secrete)

> *"Tous pour un, un pour tous."* — Les Trois Mousquetaires

A multi-agent pipeline for code audit, automated fixes, token optimization,
and adversarial red teaming — all built to run efficiently on local hardware.

**The goal: make your projects cheaper to work on.** Deploy it into any repo and
its agent routes cheap work to local models (LM Studio / Ollama) for **0 cloud
tokens**, escalates only the hard parts to the cloud, picks tools locally, and
tells you what hardware/infra changes would cut cost further.

## 🎯 What It Does

1. **Audit** — Static analysis (dead code, duplication, complexity, secrets, boundaries)
2. **Fix** — Automated corrections with verification
3. **Optimize** — Per-project skill filtering, token reduction
4. **Red Team** — Adversarial agents that challenge the Blue Team
5. **Route local↔cloud** — Auto effort estimate sends cheap tasks to local LLMs,
   hard ones to the cloud (DeepSeek/GLM/Nemotron/Grok/Gemma); fusion makes them collaborate
6. **Deploy** — One command wires the whole stack into any project via MCP

## ⚡ Deploy into your project

```bash
python -m skills.bootstrap.cli /path/to/your-project   # wire MCP tools, audit directives, write .botte config
python -m skills.infra_advisor.cli auto .              # one-pass cost audit (directives + infra + duplication)
python -m skills.llm_backends.cli audit --fresh        # what local models can this machine run?
```

After deploy, restart your agent in the project — it gains the `botte-llm` MCP
tools: `auto_route`, `local_chat`, `fusion`, `find_skills`, `infra_tips`,
`auto_audit`, `audit_local_usage`, and more.

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
| `fallow_like/` | 8 static analyzers (dead code, dup, complexity, secrets, boundaries, etc.) | Code quality |
| `skill_project_optimizer/` | Per-project skill filtering, token profiling | -73% skill tokens |
| `directives_audit/` | **P16** — Audit agent-guidance files (CLAUDE.md/AGENTS.md/specs, md+html) | Avoid blind agent runs |
| `skill_finder/` | **P18** — Find relevant skills/tools for a task locally (0 cloud tokens) | -100% selection cost |
| `bootstrap/` | **P19** — Deploy the whole stack into a project (one command) | Makes it real |
| `infra_advisor/` | **P20** — Hardware/software/MCP cluster tips + auto audit (ASCII diagram) | Cut cost beyond code |
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
│   ├── fallow_like/               # 8 static analyzers
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

## 📜 License

MIT — Use freely, improve constantly.

## 👤 Author

Sylvain Galliez ([@zedarvates](https://github.com/zedarvates))
