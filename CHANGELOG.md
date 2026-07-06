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
- **Total**: 11 micro-NN opérationnels ✅

### 🔄 Boucles rétroactives cheap (P48-P55)
- **Context windows**: fenêtres indépendantes + deltas entre étapes
- **Prefix tree**: trie de préfixes + prompt diffing entre agents
- **Harness delta**: vérification différentielle (sections modifiées seulement)
- Loop budgeter, router, cache, compression (intégrés dans les modules ci-dessus)

### 🧩 DAG/RAG optimizations (P56-P62)
- **DAG waves**: exécution par vagues synchrones (topological sort)
- **DAG pruning**: suppression des nœuds/branches inutiles (BFS)
- **DAG memoization**: cache par nœud (input hash → output)
- **RAG delta retrieval**: documents nouveaux uniquement
- **RAG query shaping**: reformulation concise (supprime le filler)
- **RAG-guided routing**: RAG → meilleur agent (keyword scoring)

### 🚀 Advanced Ideas (P63-P69)
- **A2AC**: format binaire compressé inter-agents (dictionnaire 1024 entrées, 4-bit quantization)
- **Loop Distillation**: distiller les boucles rétroactives réussies
- **Skill-Level RAG**: ne charger que les skills nécessaires à la tâche
- **Predictive Fix Planning**: prédire coût/utilité des corrections
- **Agent Memory Compression**: clustering + dedup des mémoires agents
- **Predictive Routing**: meilleur chemin d'agents avant exécution
- **Agent Knowledge Distillation**: transfert de connaissance entre agents

### 🧪 Benchmark
- `scripts/benchmark_full.py`: mesure les 14 modules
- Résultat: **81.5% compression** sur échantillons réels
- Logs: 90.2% | JSON: 92.4% | Code: 5.2% | Contexte mixte: 55.4%

### 📈 Stats
- Skills: 57 → **~90**
- Micro-NN: 4 → **11**
- Nouveaux modules: **35** (P41-P69)
- Commits cette session: **22**
- Économies réelles: **590M tokens/mois** (mai 2026)

### 🔧 Autre
- CogniARC: exploration adaptative, PuzzleStrategy, hypothèses génériques
- Kanboard-Neo: dashboard stats réels, activity feed Linear-style
- arc-human-skills: 2 747 lignes drawing improvements
- Provider Hermes `botte-proxy`: prêt à l'emploi
