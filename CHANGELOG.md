# Changelog

## v1.7.0 (2026-07-06) — Copilot Analysis Edition

### 🚀 Infrastructure Proxy (5 features)
- **Proxy mode**: `python -m skills.botte_proxy.cli proxy --port 8787`
- **Agent wrap**: `python -m skills.botte_wrap.cli wrap claude|codex|aider|opencode`
- **Output reduction**: verbosity steering + content trimming des réponses
- **CacheAligner**: normalisation des préfixes pour KV caches provider
- **Dollar savings**: MODEL_PRICES pour 20+ providers, dashboard $$$

### 📊 Pipeline optimizations (P41-P47)
- **Prefix pruner**: élague les sections de contexte inutilisées
- **Agent cache**: skip-agent quand output prédictible (hash/fingerprint/fuzzy)
- **Token shaper**: 4 niveaux de compression adaptative (aggressive→none)
- **Self-budget**: agents qui gèrent leur propre budget token
- **Context slicer**: segmentation multi-window du contexte
- **Token compressor**: hashing sémantique + byte-pair pruning
- **Auto-distill**: distillation cloud → micro-NN (logistic regression pure numpy)

### 🧠 Micro-NN Belt 2.0 (7 nouveaux modèles)
- compressibility_predictor (6f→3c): niveau de compression optimal
- context_pruning_predictor (6f→2c): section à garder/couper
- skip_agent_predictor (7f→2c): exécuter ou skipper
- cloud_escalation_predictor (7f→3c): local small/big/cloud
- response_length_predictor (6f→3c): longueur de réponse
- tool_call_predictor (7f→2c): LLM seul ou avec outils
- semantic_cache_hit_predictor (7f→2c): cache hit ou miss

### 🔄 Boucles rétroactives cheap (P48-P50)
- **Context windows**: fenêtres indépendantes + deltas
- **Prefix tree**: trie de préfixes + prompt diffing
- **Harness delta**: vérification différentielle

### 🧩 DAG/RAG optimizations (P56-P62)
- **DAG waves**: exécution par vagues synchrones
- **DAG pruning**: suppression des nœuds/branches inutiles
- **DAG memoization**: cache par nœud
- **RAG delta retrieval**: documents nouveaux uniquement
- **RAG query shaping**: reformulation concise
- **RAG-guided routing**: RAG → meilleur agent

### 🧪 Benchmark
- `scripts/benchmark_full.py`: mesure les 14 modules
- Résultat: 81.5% compression sur échantillons réels

### 📈 Stats
- Skills: 57 → ~85
- Micro-NN: 4 → 11
- Commits cette session: 19
- Économies réelles: 590M tokens/mois (mai 2026)

### 🔧 Autre
- CogniARC: exploration adaptative, PuzzleStrategy, hypothèses génériques
- Kanboard-Neo: dashboard stats réels, activity feed Linear-style
- arc-human-skills: 2 747 lignes drawing improvements
- Provider Hermes `botte-proxy`: prêt à l'emploi
