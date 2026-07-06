---
name: agent-cache
description: "Cache les réponses des agents pour skipper l'exécution quand l'output est prédictible. Use when you want to cut 10-15% by avoiding redundant agent runs."
---
# Agent Cache

Skippe l'exécution d'un agent si son résultat peut être prédit.

## Stratégies de matching

| Stratégie | Description | Quand |
|-----------|-------------|-------|
| Exact hash | Même input → même output | Tâches déterministes |
| Fingerprint | Code inchangé → résultat inchangé | Audit, linting |
| Fuzzy match | Similarité sémantique | Questions similaires |

## Usage

```bash
python -m skills.agent_cache.cli check "query" --agent audit
python -m skills.agent_cache.cli store "query" "response" --agent fix
python -m skills.agent_cache.cli stats
```
