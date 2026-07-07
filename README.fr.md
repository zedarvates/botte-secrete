# Botte Secrète — README (Français)

> Traduction française du README principal. Le README anglais reste la référence.

## Quoi

Plateforme d'optimisation de tokens pour workflows d'agents IA. 50+ skills,
6 routeurs micro-NN, 0 token cloud pour la plupart des tâches.

## Installation rapide
```bash
git clone https://github.com/zedarvates/botte-secrete
cd botte-secrete
python -m skills.bootstrap.cli .
```

## Vérification
```bash
python scripts/run_tests.py -q
# Attendu : TOTAL: 582 passed, 0 failed
python -m skills.checkup.cli .
# Attendu : directives 100/100, policy ✓
```

## Stack de routage (4 couches)
1. **Micro-NN** (~0ms, numpy) — classifie effort, route local/cloud, détecte anomalies
2. **Règles déterministes** (0 token) — heuristiques, solveurs
3. **LLM local** (Ollama / LM Studio)
4. **Cloud** — uniquement le travail complexe

## Skills principales
- `checkup` — diagnostic projet complet
- `context_profiler` — mesure du coût de préfixe
- `auto_router` — décision local/cloud avec explain
- `security_scanner` — taint analysis, patterns malveillants
- `local_harness` — exécution vérifiée, sandbox, cache KV

Voir [README.md](README.md) pour la version complète en anglais.
