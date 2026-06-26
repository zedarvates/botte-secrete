---
name: trajectory
description: "Trajectory Learning for Botte Secrète — stores solver trajectories and searches similar past optimizations to inform future decisions"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [botte, trajectory, memory, learning]
    related_skills: [solvers, trajectory-memory]
---

# Trajectory Learning for Botte Secrète

## Overview

Stocke les trajectoires d'optimisation des solveurs déterministes.
Permet de retrouver des solutions similaires déjà calculées → 0 token, 0 latence.

Compatible avec `~/.hermes/scripts/trajectory_search.py` (Hermes Trajectory Memory).

## Files

| Fichier | Rôle |
|---------|------|
| `skills/trajectory/__init__.py` | capture(), search(), load(), stats() |
| `skills/trajectory/store/trajectories.jsonl` | Stockage JSON Lines |

## Usage

```python
from skills.trajectory import capture, search, get_stats

# Capturer une trajectoire
tid = capture(
    solver="bin_pack",
    task="pack 3 database backups into 10GB capacity",
    parameters={"items": [("db1", 4), ("db2", 7), ("db3", 3)], "capacity": 10},
    result={"bins": [...], "bin_count": 2},
    latency=0.002,
    tokens_saved=500,
)

# Rechercher des trajectoires similaires
hits = search("pack items into capacity")
for h in hits:
    print(f"[{h['score']:.2f}] {h['trajectory']['task']}")

# Statistiques
stats = get_stats()
print(f"Total: {stats['total']}, Tokens saved: {stats['total_tokens_saved']}")
```

## Integration with solvers

Dans `skills/solvers/solvers.py`, chaque fonction peut capturer sa trajectoire:

```python
from skills.trajectory import capture

def assign_balanced(tasks, workers):
    result = ...  # existing logic
    capture("assign_balanced", f"assign {len(tasks)} tasks to {len(workers)} workers",
            {"tasks": tasks, "workers": workers}, result, latency=latency())
    return result
```

## Integration with Hermes

Les fichiers sont compatibles: Botte peut lire les trajectoires Hermes et vice-versa:

```python
# Lire les trajectoires Hermes
from skills.trajectory import load
hermes_trajs = load("/home/redgamer/.hermes/trajectory_store/trajectories.jsonl")
```

## Pitfalls

- **Rotation automatique** à 5000 entrées
- **TF-IDF** uniquement — pas de sémantique profonde
- **Latence** de capture < 1ms (append-only)
- **Thread-safe** pour usage concurrent
