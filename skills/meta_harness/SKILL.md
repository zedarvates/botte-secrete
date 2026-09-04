---
name: meta_harness
description: Meta-Harness orchestre les skills Botte comme des agents interchangeables dans un pipeline gouverné. Planifie → exécute en sandbox → review croisé → applique avec garde-fous et SAFE-EXIT.
tags: [orchestration, pipeline, governance, sandbox, multi-agent, safe-exit]
---

# meta_harness — orchestration multi-agent

Un meta-harness qui orchestre les skills Botte (audit, fix, counter-audit, optimize, test)
dans un pipeline gouverné. Chaque étape tourne dans son propre sandbox
(subprocess, workdir isolé). Governance = approval gates; SAFE-EXIT = budgets,
stagnation et sortie `UNCERTAIN`; rollback/snapshots restent des responsabilités
explicites du tool plane et des workflows mutatifs.

## Concept

```
USER: "audit + fix mon projet"
    │
    ▼
Meta-Harness
    ├── Orchestrator → Plan: [audit] → [review] → [fix] → [test]
    │
    ├── Sandbox 1: Porthos audit (skills/directives_audit)
    ├── Sandbox 2: Rochefort counter-audit (skills/cardinal)
    ├── Sandbox 3: d'Artagnan fix (skills/fix)
    └── Sandbox 4: run tests
    │
    ├── Governance → approval gate avant apply
    ├── SAFE-EXIT → budgets/stagnation → UNCERTAIN + skip remaining
    │
    └── Report → synthèse multi-agent + termination reason
```

## Agents disponibles

| Agent | Skill Botte | Rôle |
|-------|-------------|------|
| `porthos` | directives_audit | Audit initial |
| `rochefort` | cardinal | Contre-audit (red team) |
| `d'artagnan` | fix | Correction automatique |
| `aramis` | optimize | Optimisation token |
| `conductor` | conductor | Planification |
| `security` | security_scanner | Scan sécurité |
| `fast_context` | fast_context | Exploration repo |
| `migration_audit` | migration_audit | Vérifie la suppression réelle des chemins historiques |

## Usage

```bash
# Pipeline complet: audit → counter-audit → fix → test
python -m skills.meta_harness.cli run . audit counter-audit fix test

# Voir les pipelines disponibles
python -m skills.meta_harness.cli plans

# Lancement avec approval gate
python -m skills.meta_harness.cli run . audit fix --approval

# Étape déterministe à placer après BUILDER et avant VALIDATOR
python -m skills.meta_harness.cli run . migration-gate

# Voir l'état d'un pipeline
python -m skills.meta_harness.cli status <session_id>

# Rollback
python -m skills.meta_harness.cli rollback <session_id>
```

## API Python

```python
from skills.meta_harness import MetaHarness
from skills.safe_exit import SafeExitConfig

h = MetaHarness(
    workdir="/path/to/project",
    safe_exit_config=SafeExitConfig(
        max_iterations=12,
        max_tool_calls=48,
        max_wall_seconds=900,
    ),
)

plan = h.plan(["audit", "counter-audit", "fix", "test"])
session = h.execute(plan)

print(session.report())
if session.termination_decision == "UNCERTAIN":
    print("SAFE-EXIT:", session.termination_reason)
```

## SAFE-EXIT semantics

- Only actually executed sandbox steps consume an iteration/tool-call unit.
- Dependency/governance skips do not consume the execution budget.
- Equivalent repeated failures can terminate the trajectory early.
- After `UNCERTAIN`, every still-pending step is recorded as skipped and is not executed.
- The session JSON persists `termination_decision` and `termination_reason`.
- Starting a new plan after `UNCERTAIN` is a supervisor decision; the current run must not silently reset its budget.
- SAFE-EXIT does not replace OS/container network isolation or destructive-operation snapshot gates.

## Architecture

```
meta_harness/
├── orchestrator.py   — Planification + dispatch + SAFE-EXIT enforcement
├── runner.py         — Sandbox subprocess + timeout + workdir isolé
├── governance.py     — Approval gates
├── session.py        — Persistance + historique + termination state
├── cli.py            — argparse CLI
├── test_meta_harness.py
└── test_safe_exit_integration.py
```
