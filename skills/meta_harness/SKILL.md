---
name: meta_harness
description: Meta-Harness orchestre les skills Botte comme des agents interchangeables dans un pipeline gouverné. Planifie → exécute en sandbox → review croisé → applique avec garde-fous. Inspiré d'Omnigent mais 100% Botte-native.
tags: [orchestration, pipeline, governance, sandbox, multi-agent]
---

# meta_harness — orchestration multi-agent

Un meta-harness qui orchestre les skills Botte (audit, fix, counter-audit, optimize, test)
dans un pipeline gouverné. Chaque étape tourne dans son propre sandbox
(subprocess, workdir isolé). Governance = approval gates + budgets + rollback.

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
    │
    └── Report → synthèse multi-agent
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
from skills.meta_harness import MetaHarness, PipelinePlan, Step, Sandbox

# Créer un harness
h = MetaHarness(workdir="/path/to/project")

# Planifier un pipeline
plan = h.plan(["audit", "counter-audit", "fix", "test"])

# Exécuter
session = h.execute(plan, approval=False)

# Voir le rapport
print(session.report())
```

## Architecture

```
meta_harness/
├── orchestrator.py   — Planification pipeline + dispatch
├── runner.py         — Sandbox subprocess + workdir isolé
├── governance.py     — Garde-fous, budgets, rollback
├── session.py        — Persistance + historique
├── cli.py            — argparse CLI
└── test_meta_harness.py
```
