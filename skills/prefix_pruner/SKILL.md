---
name: prefix-pruner
description: "Prefix prune le contexte — arbre de préfixes, diffing, élague les sections inutilisées. Use when you want to cut 5-10% more tokens by removing dead context."
---
# Prefix Pruner

Élimine les sections de contexte que l'agent n'utilise jamais.

## Stratégies

| Stratégie | Description | Gain |
|-----------|-------------|------|
| `auto` | Prefix tree + usage tracking | 5-10% |
| `aggressive` | Supprime toute section < 0.3 usefulness | 10-15% |
| `conservative` | Ne supprime que les sections jamais utilisées | 2-5% |

## Usage

```bash
python -m skills.prefix_pruner.cli prune < context.txt
python -m skills.prefix_pruner.cli tree
python -m skills.prefix_pruner.cli stats
```
