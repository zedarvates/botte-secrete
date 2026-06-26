---
name: fast_context
description: FastContext Agent — exploration repo déterministe. Parse une requête d'exploration → READ/GLOB/GREP ciblés → rapport compact (fichier:ligne:score). Remplace 56% des appels LLM de type "read/search" par des opérations stdio à ~5ms, 0 token. Use when the agent needs to understand a codebase, find patterns, locate imports, or gather context without an LLM call.
tags: [exploration, context, search, token-optimization, stdio]
---

# FastContext Agent — exploration repo

Un sous-agent d'exploration déterministe qui sépare la **collecte de contexte**
du **raisonnement**. Au lieu de laisser l'agent principal dépenser 56% de ses
tokens en READ/GLOB/GREP, FastContext gère ça en **~5ms, 0 token**.

Inspiré par **Microsoft FastContext-1.0-4B-SFT** mais 100% déterministe
(stdlib Python, pas de LLM, pas de GPU).

## Usage

```bash
# Explorer un dossier
python -m skills.fast_context.cli explore /path/to/project "find DB connection patterns"

# Types de requête supportés
python -m skills.fast_context.cli explore . "find all imports in main.py"
python -m skills.fast_context.cli explore . "understand function: calibrate()"
python -m skills.fast_context.cli explore . "where are the tests?"
python -m skills.fast_context.cli explore . "queue usage patterns"
python -m skills.fast_context.cli explore . "audit security: eval, exec, shell"

# Mode verbeux
python -m skills.fast_context.cli explore . "find async patterns" --verbose

# Limiter les résultats
python -m skills.fast_context.cli explore . "import pathlib" --max-results 10

# Utiliser le cache
python -m skills.fast_context.cli explore . "class FastContext" --cache
```

## API Python

```python
from skills.fast_context import explore, cached_explore
from skills.fast_context import discover_query_type, QueryType

# Exploration simple
results = explore(".", "find DB connection patterns")
# → [{"file": "src/db.py:15", "snippet": "...", "score": 0.92, "type": "import"}, ...]

# Avec cache
results = cached_explore(".", "find async patterns", ttl=60)

# Découverte du type de requête
qt = discover_query_type("find all imports")
# → QueryType.IMPORTS
```

## Types de requête

| Type | Mots-clés | Action |
|------|-----------|--------|
| `IMPORTS` | import, dependency, require | grep imports + suggest files |
| `FUNCTION` | function, method, def, understand | grep def → contexte fichier |
| `TESTS` | test, spec, unittest | glob test_* + grep |
| `PATTERN` | pattern, usage, find, where | grep générique |
| `SECURITY` | security, audit, eval, malicious | grep dangereux |

## Architecture

```
FastContext Agent
  ┌─────────────────────────────────┐
  │  agent.py                       │
  │  - discover_query_type(query)   │
  │  - explore(query, path) → list  │
  ├─────────────────────────────────┤
  │  readers.py                     │
  │  - fast_read(file, lines)       │
  │  - fast_glob(pattern, root)     │
  │  - fast_grep(pattern, root)     │
  ├─────────────────────────────────┤
  │  ranker.py                      │
  │  - score(file, match, query)    │
  │  - rank_results(results)        │
  ├─────────────────────────────────┤
  │  compiler.py                    │
  │  - compile_report(results)      │
  │  - format_compact(results)      │
  ├─────────────────────────────────┤
  │  store.py                       │
  │  - LRUCache(ttl=30)             │
  └─────────────────────────────────┘
```

## Économie tokens estimée

| Type requête | Avant (LLM) | Après (FastContext) | Économie |
|-------------|-------------|-------------------|----------|
| Imports | ~800 tokens | 0 token | -100% |
| Comprendre fonction | ~1200 tokens | 0 token | -100% |
| Trouver tests | ~400 tokens | 0 token | -100% |
| Pattern search | ~600 tokens | 0 token | -100% |
| Audit sécurité | ~2000 tokens | 0 token | -100% |

**~5000 tokens/session** économisés (estimé sur 5 explorations par session).

## Pitfalls

1. **Ne remplace pas LLM pour compréhension complexe** — FastContext livre du
   contexte brut (fichier:ligne:snippet). Le LLM principal doit encore raisonner
   dessus. C'est le but : le LLM ne fait QUE raisonner.
2. **Cache TTL** — Le cache LRU évite de rescanner 30 fois le même fichier dans
   la même session. TTL par défaut: 30s. Passer `--no-cache` pour forcer.
3. **Gros repos** — Pour les repos >1000 fichiers, `fast_grep` utilise
   `subprocess.run("grep -rl ...")` plutôt qu'un glob Python (10x plus rapide).
4. **Binaire/symlinks** — Skip automatiquement les fichiers binaires, .git/,
   node_modules/, __pycache__/, .venv/.
