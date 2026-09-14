# 🟥 Les Mousquetaires du Cardinal — Red Team Adversarial

> *"Un contre tous, tous contre un."*

## Concept

L'équipe **rouge** qui attaque le travail de l'équipe **bleue** (Mousquetaires d'Artagnan).
Chaque agent du Cardinal cible un Mousquetaire spécifique et cherche ce qu'il a manqué.

**Inspiré de :** Google Co-Scientist (debate), Red Teaming LLM, Adversarial Multi-Agent

## Architecture

```
Équipe Bleue                   Équipe Rouge
🥊 Porthos (Audit)    ←→      🗡️ Rochefort (Contre-audit)
⚔️ d'Artagnan (Fix)   ←→      🔪 Milady (Contre-fix)
📿 Aramis (Optimize)  ←→      🕯️ Comte de Wardes (Contre-optimisation)
👑 Athos (Chef)       ←→      👑 Le Cardinal (Chef Rouge)
```

## Les 3 Agents du Cardinal

| Agent | Cible | Rôle | Personnalité |
|-------|-------|------|-------------|
| 🗡️ **Rochefort** | Porthos | Trouver les faux négatifs de l'audit | Méthodique, suspicieux |
| 🔪 **Milady** | d'Artagnan | Trouver les régressions des fixes | Rusée, sceptique |
| 🕯️ **Comte de Wardes** | Aramis | Trouver les sur-optimisations | Calculateur, froid |

## Pré-Prompts

Chaque agent a un pré-prompt adversarial :
- `prompts/rochefort.md` — Contre-audit (faux négatifs, appels dynamiques, edge cases)
- `prompts/milady.md` — Contre-fix (régressions, fixes incomplets, effets de bord)
- `prompts/comte_de_wardes.md` — Contre-optimisation (sur-optimisation, skills mal exclus)
- `prompts/cardinal.md` — Orchestration rouge (coordination, verdict)

## Workflow

The host orchestrates the role prompts and produces the Blue/Red reports.
To consolidate those existing reports with the provided script:

```bash
python skills/cardinal/scripts/cardinal_confront.py ./blue-reports ./red-reports
```

See [SKILL.md](SKILL.md) for required files and accepted field aliases, and
[effects.json](effects.json) for consequences and reuse limits. Incomplete or
malformed inputs return exit code 2 without replacing a prior confrontation.
The score summarizes supplied findings; it does not authenticate the reviews
or establish that their tests ran. A zero exit also covers unfavorable verdicts.

## Ce que chaque agent cherche

### Rochefort (vs Porthos)
- Faux négatifs (Porthos a dit "OK" mais c'est pas OK)
- Appels dynamiques (`getattr`, `eval`, `importlib`)
- Code mort appelé via réflexion/hooks
- Race conditions, edge cases
- Fichiers non scannés

### Milady (vs d'Artagnan)
- Régressions (fix X a cassé Y)
- Fixes incomplets (code commenté mais encore appelé)
- Syntax errors après fix
- Imports cassés
- Effets de bord

### Comte de Wardes (vs Aramis)
- Sur-optimisations (code supprimé qui était utilisé)
- Skills mal exclus (.skills-profile trop restrictif)
- Faux positifs de dead code
- Optimisations qui cassent la lisibilité

## Format de Sortie

### RedTeamReport (Le Cardinal)
```json
{
  "blue_score": 65,
  "verdict": "PARTIELLEMENT FIABLE",
  "red_findings": 12,
  "rochefort": {"false_negatives": 3, "underestimated": 2},
  "milady": {"regressions": 2, "incomplete_fixes": 1},
  "conte_de_wardes": {"over_optimizations": 2, "wrongly_excluded_skills": 2}
}
```

## Quand l'utiliser

| Scénario | Utiliser ? |
|----------|-----------|
| Code critique (sécurité, finance) | ✅ Toujours |
| Avant release majeure | ✅ Oui |
| Health score < 70 | ✅ Oui — l'équipe bleue a peut-être raté des choses |
| Health score > 90 | ❌ Overkill |
| Prototype / POC | ❌ Non |

## Structure

```
skills/cardinal/
├── __init__.py
├── prompts/
│   ├── rochefort.md          # 🗡️ Contre-audit
│   ├── milady.md             # 🔪 Contre-fix
│   ├── comte_de_wardes.md    # 🕯️ Contre-optimisation
│   └── cardinal.md           # 👑 Orchestration rouge
├── scripts/
│   └── cardinal_confront.py  # Script de confrontation
└── README.md
```
