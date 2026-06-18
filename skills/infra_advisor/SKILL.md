---
name: infra_advisor
description: Audit the local cluster's hardware/software/MCP setup and recommend changes that cut token cost — GPU upgrades, Hailo NPU for vision, moving the inference node to Linux, running Qdrant locally, wiring MCP — with an ASCII cluster diagram. Also provides an auto one-pass audit (directives + infra + code duplication + skills) on the project. Use when the user asks how to reduce token/usage cost via hardware/infra, wants cluster setup tips, an ASCII diagram of their setup, or a quick all-in-one audit.
---

# infra_advisor — cut token cost beyond the code

Most audits only look at code. This looks at the **machine and the local cluster**
and recommends concrete hardware/software/infra changes that move work off paid
cloud models — then bundles a fast one-pass audit of the project.

## Commands

```bash
# Cluster tips + ASCII diagram
python -m skills.infra_advisor.cli tips
python -m skills.infra_advisor.cli tips --subnet --json

# One-pass audit on the project where Botte Secrète is installed
python -m skills.infra_advisor.cli auto .
python -m skills.infra_advisor.cli auto /path/to/project --json
```

## Infra tips (rules, prioritized P0→P3)

- **Install a local LLM** (LM Studio/Ollama) if none — the foundation for any saving.
- **Add/upgrade a GPU** (≥12-16 GB VRAM) → run a 7-14B coder locally.
- **Add a Hailo-8 / 8L / 10 NPU** → vision (detection/OCR/PDF) at ~0 tokens via `media_loader`.
- **Move the always-on inference node to Linux/WSL2** → no forced Windows reboots/updates
  killing the endpoint; more free VRAM/RAM.
- **Run Qdrant locally** → unlock the semantic response cache (-60% repeats).
- **Dedicate the strongest host** as a shared inference node for all projects.
- **Wire the MCP server** (`bootstrap`) so the agent actually uses the local tools.

Each tip carries `why` and an `impact` (expected token/cost effect). An ASCII
cluster diagram is rendered by default (`--json` for machine-readable).

## Auto audit

`auto` combines the cheap, reliable passes into one report:
**directives** health (`directives_audit`) · **infra** tips + diagram · **duplicate
function bodies** across files (stdlib AST, free) · **skill catalog** size · plus
pointers to deeper passes (full `mousquetaires`/fallow pipeline, `skill_project_optimizer`,
`understand-anything`, `botte` terminal compression).

Exposed via [[llm_mcp]] as `infra_tips` and `auto_audit`. Related: [[bootstrap]],
[[llm_backends]], [[directives_audit]], [[skill_finder]].
