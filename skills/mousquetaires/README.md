# ⚔️ Les Quatre Mousquetaires — Multi-Agent Pipeline

> *"Tous pour un, un pour tous !"*

## Concept

4 agents spécialisés qui travaillent ensemble sur un projet :
**Audit → Fix → Optimisation → Synthèse**

Chaque agent a un rôle, une personnalité et des outils dédiés.
Inspiré du papier Google Co-Scientist (Nature, 2025) transposé au code.

## Les 4 Mousquetaires

| Agent | Rôle | Personnalité | Outils |
|-------|------|-------------|--------|
| 🥊 **Porthos** | Auditeur | Rigoureux, méthodique | fallow-like, scanner, analyzers |
| ⚔️ **d'Artagnan** | Développeur | Efficace, pragmatique | terminal, write_file, patch |
| 📿 **Aramis** | Optimiseur | Réfléchi, stratégique | skill-project-optimizer, profiler |
| 👑 **Athos** | Orchestrateur | Sage, calme | delegate_task, todo, synthèse |

## Pré-Prompts

Chaque agent est guidé par un **pré-prompt** qui définit :
- Son identité et personnalité
- Son rôle unique (ce qu'il fait et ne fait PAS)
- Ses outils principaux
- Son format de sortie structuré
- Ses anti-patterns (REJECTED) et bonnes pratiques (CHOSON)

```
prompts/
├── porthos.md      # Pré-prompt Porthos (audit)
├── dartagnan.md    # Pré-prompt d'Artagnan (fix)
├── aramis.md       # Pré-prompt Aramis (optimisation)
└── athos.md        # Pré-prompt Athos (orchestration)
```

## Workflow

```
User: "Audit et optimise mon projet"
  ↓
👑 Athos reçoit le goal
  ↓
🥊 Porthos audite le projet
  → fallow-like scan (dead code, duplication, complexity, secrets)
  → AuditReport (JSON + markdown)
  ↓
⚔️ d'Artagnan corrige les bugs
  → Lit l'AuditReport
  → Applique les fixes (code mort, etc.)
  → FixReport (JSON)
  ↓
📿 Aramis optimise
  → skill-project-optimizer (token savings)
  → .skills-profile généré
  → OptimizationPlan (JSON + markdown)
  ↓
👑 Athos synthétise
  → ConsolidatedReport (1 page)
  → Plan d'action P0/P1/P2
```

## Utilisation

### CLI Direct

```bash
# Audit seul (Porthos)
python -m skills.mousquetaires.cli audit ~/projects/mon-projet --output ./reports

# Fix seul (d'Artagnan)
python -m skills.mousquetaires.cli fix ~/projects/mon-projet --audit ./reports/audit-report.json

# Optimisation seule (Aramis)
python -m skills.mousquetaires.cli optimize ~/projects/mon-projet --output ./reports

# Pipeline complet (Athos orchestre les 3)
python -m skills.mousquetaires.cli run ~/projects/mon-projet --output ./reports

# Pipeline partiel (skip phases)
python -m skills.mousquetaires.cli run ~/projects/mon-projet --skip-fix

# Statut des agents
python -m skills.mousquetaires.cli status
```

### Depuis Hermes (delegate_task)

```python
# Lancer Porthos en subagent
delegate_task(
    goal="Tu es Porthos, l'Auditeur. Audit le projet ~/projects/mon-projet. "
         "Utilise fallow-like pour scanner. Produis un AuditReport JSON. "
         "Ne corrige PAS le code — identifie les problèmes.",
    context=load_prompt("porthos"),
    toolsets=["terminal", "file"],
)

# Lancer d'Artagnan en subagent
delegate_task(
    goal="Tu es d'Artagnan, le Développeur. Lis audit-report.json et "
         "corrige les findings. Applique le workflow OBLIGATOIRE: "
         "writing-plans → code-rules → fix → vérifier.",
    context=load_prompt("dartagnan"),
    toolsets=["terminal", "file"],
)

# Lancer Aramis en subagent
delegate_task(
    goal="Tu es Aramis, l'Optimiseur. Optimise ~/projects/mon-projet. "
         "Utilise skill-project-optimizer. Produis un OptimizationPlan.",
    context=load_prompt("aramis"),
    toolsets=["terminal", "file"],
)
```

## Formats de Sortie

### AuditReport (Porthos)
```json
{
  "project": "...",
  "health_score": 72,
  "health_grade": "C",
  "findings": {
    "critical": [...],
    "error": [...],
    "warning": [...],
    "info": [...]
  },
  "dead_code": [...],
  "duplication": [...],
  "complexity": [...],
  "secrets": [...],
  "recommendations": [...]
}
```

### FixReport (d'Artagnan)
```json
{
  "fixed": 5,
  "total": 12,
  "remaining": ["file:line — reason"]
}
```

### OptimizationPlan (Aramis)
```json
{
  "matched_skills": [("writing-plans", "always"), ...],
  "excluded_skills": [("ascii-video", "not matched"), ...],
  "stats": {
    "total_available": 76606,
    "total_loaded": 20645,
    "savings": 55961,
    "savings_percent": 73
  }
}
```

### ConsolidatedReport (Athos)
```json
{
  "global_score": 72,
  "phases": {
    "audit": {"status": "complete"},
    "fix": {"status": "complete"},
    "optimize": {"status": "complete"}
  }
}
```

## Token Savings

| Phase | Tokens (typical) | Savings |
|-------|-----------------|---------|
| Porthos audit | ~2,000 | — |
| d'Artagnan fix | ~3,000 | — |
| Aramis optimize | ~1,500 | — |
| Athos synthesis | ~1,000 | — |
| **Total pipeline** | **~7,500** | **vs ~76K (all skills) = 90%** |

## Intégration avec botte-secrete

- **fallow-like** → Utilisé par Porthos (8 analyzers)
- **skill-project-optimizer** → Utilisé par Aramis (scanner, profiler, optimizer)
- **code-rules** → Chargé par d'Artagnan (workflow obligatoire)
- **karpathy-guidelines** → Utilisé par tous (anti-patterns)

## Structure

```
skills/mousquetaires/
├── __init__.py
├── cli.py                    # CLI principale (typer + rich)
├── prompts/
│   ├── porthos.md            # Pré-prompt Porthos
│   ├── dartagnan.md          # Pré-prompt d'Artagnan
│   ├── aramis.md             # Pré-prompt Aramis
│   └── athos.md              # Pré-prompt Athos
├── scripts/
│   ├── porthos_audit.py      # Script audit (fallow-like)
│   ├── dartagnan_fix.py      # Script fix (auto-fix)
│   └── aramis_optimize.py    # Script optimisation
├── templates/
│   ├── audit-report.md       # Template rapport audit
│   ├── fix-report.md         # Template rapport fix
│   ├── optimization-plan.md  # Template plan optimisation
│   └── consolidated-report.md # Template rapport final
└── README.md
```

## Prérequis

```bash
pip install typer rich pydantic pydantic-settings networkx tree-sitter
```

## Anti-Patterns

```
REJECTED: Un seul agent qui fait tout.
CHOSEN:   4 agents spécialisés, chacun son rôle.

REJECTED: Porthos corrige le code pendant l'audit.
CHOSEN:   Porthos audite. d'Artagnan corrige.

REJECTED: Aramis optimise sans mesurer.
CHOSEN:   Aramis mesure avant et après.

REJECTED: Athos fait le travail lui-même.
CHOSEN:   Athos délègue et synthétise.
```
