# Caveman — Télégraphic Output Compression (Axe 1)

Force le modèle à répondre en style télégraphique pour réduire de **65-75% les output tokens**. Inspiré du projet Caveman (69k⭐ GitHub).

## Niveaux

| Niveau | Description | Économie | Usage |
|---|---|---|---|
| `light` | Drop filler only ("Sure!", "Let me...") | ~30% | Queries simples |
| `full` | Fragments, pas de phrases complètes | ~65% | Mode par défaut |
| `ultra` | Télégraphique, acronymes, pas d'articles | ~75% | Gros volumes |
| `classical` | Chinois classique (le plus dense) | ~80% | Max savings |

## System Prompts

Les prompts sont dans `prompts/` — injectés dans le system prompt du modèle.

## Usage

```bash
# Compresser un fichier
python -m skills.caveman.cli compress mon_fichier.md --level ultra

# Stats de compression
python -m skills.caveman.cli stats

# Générer le system prompt pour un niveau
python -m skills.caveman.cli prompt --level full
```

## Integration

Ce skill s'intègre avec `auto_router/effort.py` et `context_budget/` pour activer
automatiquement le bon niveau selon le budget token restant.
