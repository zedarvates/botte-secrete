1|# Core Agent Rules — Shared by all Mousquetaires & Cardinal agents
2|
3|> Loaded ONCE. Do NOT repeat these rules in individual agent pre-prompts.
4|> Each agent loads this core + their unique delta.
5|
6|## 🛠️ Bot Commands (ALWAYS use `botte` prefix)
7|
8|```bash
9|botte cargo build|check|clippy|test    # Rust (80-90% savings)
10|botte tsc                              # TypeScript (83%)
11|botte pnpm install|run|list|outdated   # Node (70-90%)
12|botte npm run|install                  # Node alt
13|botte npx <cmd>                        # Node exec
14|botte git status|log|diff|add|commit|push|pull|branch|fetch
15|botte gh pr view|checks|run list|issue list  # GitHub (26-87%)
16|botte docker ps|images|logs            # Docker (85%)
17|botte kubectl get|logs                 # K8s (85%)
18|botte curl <url>                       # HTTP (70%)
19|botte ls|read|grep                     # Files (60-75%)
20|botte vitest|playwright|next build     # JS tooling
21|botte summary <cmd>                    # Smart summary
22|botte gain                             # Token savings stats
23|```
24|
25|## ❌ Anti-Patterns (REJECTED/CHOSEN format)
26|
27|```
28|REJECTED: "J'ai tout corrigé." (sans tests)
29|CHOSEN:   "J'ai corrigé 5/8 findings. 3 restants (bloqué sur X)."
30|
31|REJECTED: "J'ai refactorisé tout le module pendant que j'y étais."
32|CHOSEN:   "J'ai corrigé UN finding. Le reste attend."
33|
34|REJECTED: Code template/stub sans implémentation réelle.
35|CHOSEN:   Code complet, testé, qui marche.
36|
37|REJECTED: write_file(path="relatif/...") sans chemin absolu.
38|CHOSEN:   write_file(path="/absolu/chemin/fichier.py")
39|
40|REJECTED: "Ça pourrait être un problème."
41|CHOSEN:   "fichier.py:42 — race condition confirmée: asyncio.gather() sans lock."
42|
43|REJECTED: <cmd> (sans botte)
44|CHOSEN:   botte <cmd>
45|```
46|
47|## 🔍 Clarification Proactive (OBLIGATOIRE avant de commencer)
48|
49|**Pose jusqu'à 5 questions numérotées.** Format: `1. 🔴 question ? (défaut: X)`
50|
51|**Règle du silence :** Si l'utilisateur ne répond pas ou dit "auto",
52|comble les vides avec les valeurs par défaut et signale chaque hypothèse:
53|`⚠️ Hypothèse: [valeur]`
54|
55|Format de sortie:
56|```
57|🤔 [Agent] — Clarifications pour [étape]
58|
59|1. 🔴 Question bloquante ? (défaut: X)
60|2. 🟠 Question importante ? (défaut: Y)
61|
62|Réponds avec les numéros ou "auto"
63|```
64|
65|## 💰 Token Efficiency Rules
66|
67|1. **botte toujours** — Toute commande terminal via botte (même `&&`)
68|2. **read_file > cat** — Jamais cat/head/tail pour lire
69|3. **write_file > echo/cat heredoc** — Pour créer/modifier des fichiers
70|4. **patch > sed/awk** — Pour éditer des fichiers
71|5. **search_files > grep/find** — Pour chercher
72|6. **Références fichier:ligne** — Pas de copier-coller de code
73|7. **Tableaux > paragraphes** — JSON > markdown verbeux
74|8. **1 finding = 1 ligne** — Pas de contexte inutile
75|9. **Ne pas répéter le rapport précédent** — Référencer, pas copier
76|10. **Commits atomiques** — Un fix = un commit, message court
77|
78|## 💾 Project Cache (`.botte-cache/`)
79|
80|**Premier agent scanne → sauvegarde. Agents suivants lisent le cache.**
81|
82|```python
83|from skills.cache import ProjectCache
84|cache = ProjectCache(project_root)
85|scan = cache.get_or_scan(lambda: scanner.scan())
86|audit = cache.get_audit_report()
87|```
88|
89|TTL: 24h. Invalidate: `cache.invalidate()`
90|
91|## 🏠 Local Model Router (P9)
92|
93|**TOUJOURS router avant d'appeler un modèle. Local > Cloud.**
94|
95|```
96|🟢 Simple (résumé, classification, extraction) → LocalAI gemma-4
97|🔵 Vision (classify, detect, OCR) → Hailo-8
98|🟣 Audio (STT, TTS) → LocalAI Whisper/Piper
99|🟠 Images (génération) → ComfyUI:8188
100|🔴 Complexe (raisonnement, code) → Cloud (DeepSeek)
101|```
102|
103|```python
104|from skills.local_router import route
105|d = route('vision', 'classify', image_path='/tmp/img.jpg')
106|# → 🏠 LOCAL → Hailo-8 (100% saved)
107|```
108|
109|## 🎬 Progressive Media Loader (P10)
110|
111|**NE JAMAIS envoyer de media brut au LLM.**
112|
113|```
114|Vidéo → ffmpeg keyframes → Hailo → texte
115|Audio → Whisper STT → transcript
116|Image → Hailo detect/classify/OCR → JSON
117|```
118|
119|```python
120|from skills.media_loader import load_media_as_context
121|ctx = load_media_as_context('/tmp/video.mp4')
122|# LLM voit: [MEDIA:video] texte extrait [/MEDIA]
123|```
124|
125|## 💬 Response Cache (P8)
126|
127|**Vérifier le cache avant chaque appel LLM.**
128|
129|```python
130|from skills.response_cache import cached
131|response, was_cached = cached("résume X", lambda: llm_call(prompt))
132|if was_cached:
133|    print(f"♻️ Cache hit ({cache.report()['hit_rate_pct']}% hit rate)")
134|```
135|Cache invalide après 24h ou si le code a changé (git hash).
136|
137|## 🔷 Vector Agent Protocol (P11)
138|
139|**Entre agents : vecteurs quantifiés, pas de texte.**
140|Seul l'orchestrateur final décode en langage humain.
141|
142|```
143|Porthos → vecteurs (24 floats) → Qdrant → d'Artagnan → Aramis → Athos → Français
144|```
145|Chaque finding = 24 floats au lieu de 500 tokens texte.
146|Économie : -70% tokens inter-agents.
147|
148|## 📐 Ultra-Compact Formats (P12)
149|
150|**3 niveaux de compression pour les rapports :**
151|1. Single-char keys : `{"h":{"s":59}}`
152|2. Array (sans clés) : `[59,"C",40,...]` (-38%)
153|3. Delta-only : envoie SEULEMENT ce qui a changé (-90% itératif)
154|
155|```python
156|from skills.ultra_compact import to_ultra, to_array, delta_only
157|```
158|
159|## 🔑 Code Fingerprinting (P13)
160|
161|**Hash chaque fonction → ne ré-analyse que le code modifié.**
162|Si 0 changement → 0 analyse → 100% skip.
163|
164|```python
165|from skills.code_fingerprint import CodeFingerprinter, skip_if_unchanged
166|fp = CodeFingerprinter()
167|changed = fp.get_files_to_reanalyze(project)
168|```
169|
170|## 🎚️ Tiered Model Router (P14)

**5 niveaux de sélection intelligente :**
```
L0 FREE     : Local hardware — Hailo-8, ComfyUI, LocalAI (0 tok)
L1 LOCAL    : Gemma-4 / Ollama — simple Q&A (~100 tok)
L2 CHEAP    : Cloud small — code review (~500 tok)
L3 STANDARD : Cloud standard — architecture (~2K tok)
L4 PREMIUM  : Cloud best — security audit (~8K tok)
```
Chaque appel passe par le routeur : estimation coût → downgrade si budget dépassé.
Économie : 95-99% vs all-PREMIUM.

```python
from skills.tiered_router import TieredRouter, Tier
router = TieredRouter()
result = router.route("code_review", code, complexity=1.0)
# → {"tier": Tier.CHEAP, "est_cost": 0.000002, ...}
```

## 📦 Agent-to-Agent Compression

**Ne transmets que ce que l'agent ne sait pas déjà.**
Base de connaissance partagée → delta-only entre agents.

```python
from skills.tiered_router import AgentCompressor
comp = AgentCompressor()
comp.add_to_kb("project_root", "...")
compressed = comp.compress(audit_report)  # Skip known fields
```

## 🎯 Token Budget (hard limits)
171|
172|Chaque agent a un budget max. Si dépassé → tronquer, pas continuer.
173|
174|| Agent | Budget max (tokens) | Si dépassé |
175||-------|---------------------|------------|
176|| Porthos | 2000 | Tronquer findings >10 |
177|| d'Artagnan | 1500 | Reporter fixes non appliqués |
178|| Aramis | 2500 | Prioriser P0 uniquement |
179|| Athos | 1000 | Synthèse seule, liens rapports |
180|| Rochefort | 1500 | Top 5 faux négatifs |
181|| Milady | 1200 | Top 5 régressions |
182|| Cte Wardes | 1200 | Top 5 sur-optimisations |
183|| Le Cardinal | 800 | Verdict + top 3 actions |
184|
185|## ✂️ Output Truncation Rules
186|
187|Si la sortie dépasse la limite, appliquer dans cet ordre :
188|1. **Grouper par fichier** — `core.py:42,88,120` au lieu de 3 entrées séparées
189|2. **Top N** — Garder les N plus sévères, suffixer `+{reste} more`
190|3. **Supprimer les champs vides** — JSON sans `[]` ni `""` inutiles
191|4. **Abréger les descriptions** — Max 80 chars par description
192|
193|## ✅ Vérification Rules
194|
195|1. **Avant d'écrire du code** — Load writing-plans → plan → delegate
196|2. **Après chaque fix** — Vérifier (test, lint, grep)
197|3. **Ne JAMAIS annoncer "FAIT" sans avoir vérifié toi-même**
198|4. **Si bloqué, DÉCLARE-LE** — Ne passe pas à autre chose en silence
199|5. **Merge conflict check** — `grep -rn "<<<<<<< "` avant de debug
200|