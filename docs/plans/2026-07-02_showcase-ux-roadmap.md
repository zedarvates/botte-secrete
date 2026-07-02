# 🧦 Botte Secrète — Roadmap Showcase & UX

> **Date :** 2 juillet 2026
> **Objectif :** rendre visible ce que la plateforme fait déjà — effet "wow" en
> moins de 60 secondes, sans rien réécrire du moteur.
> **Prompt source (amélioré) :** voir Annexe A en bas de ce fichier.

---

## 🎯 Vision

Le moteur (4 filtres, NN belt, harness anti-hallucination) est solide mais
**invisible** : ses décisions se prennent en ~0 ms et ne laissent aucune trace
regardable. Cette roadmap ajoute une couche *vitrine* au-dessus des briques
existantes, dans cet ordre de dépendance :

```
P0  Event log unifié (.botte/events.jsonl)      ← fondation de tout le reste
 ├─ P1  Demo mode interactif (TUI live)
 ├─ P2  Dashboard : version terminal + --watch  (HTML existe déjà)
 └─ P5b Session replay ("boîte noire")
P3  botte doctor (assemblage checkup + machine + rapport)
P4  Hermes compatibility + proposition d'intégration au repo hermes-agent
P5  Idées complémentaires (bench, GitHub Action, statusline, fleet view)
```

---

## P0 — Event log unifié (fondation) 🔴 prioritaire ✅ fait (2026-07-02)

> `skills/events/` livré : writer JSONL append-only, rotation 5 Mo, `tail`/`log`/
> `clear`/`follow_events`. Câblé dans `auto_router.run()` (route + escalate) et
> `cache.ProjectCache.get()` (hit/miss). 7 tests, 625/625 dans la suite globale.

**Constat :** demo mode, dashboard live et replay ont tous besoin de la même
chose : un flux d'événements de décision. Aujourd'hui chaque skill garde ses
chiffres dans son coin (`control_loop`, `metrics`, cache).

**Livrable :** `skills/events/` — un writer JSONL append-only, ~100 lignes.

```
.botte/events.jsonl   # 1 ligne = 1 décision
{"ts": ..., "kind": "route",    "filter": 1, "nn": "effort_classifier", "out": "local", "conf": 0.93, "tokens_saved": 210}
{"ts": ..., "kind": "cache",    "hit": true, "key": "...", "tokens_saved": 850}
{"ts": ..., "kind": "escalate", "from": "local", "to": "cloud", "reason": "verification_failed"}
{"ts": ..., "kind": "nn_out",   "model": "binary_router", "probs": [0.91, 0.09]}
```

**Points d'émission** (1-2 lignes chacun) : `auto_router.route()`,
`llm_mcp` (auto_route/local_chat/fusion), le cache, le harness local
(escalations), `botte_nn.predict()`.

- Effort : **S** (petit) — c'est un logger, pas un système.
- Rotation : garder N derniers Mo, comme `.botte-cache`.
- 0 dépendance nouvelle, 0 réseau, cohérent avec la promesse "no telemetry"
  (le fichier reste local, jamais envoyé).

---

## P1 — Demo mode interactif 🎬 ✅ fait (2026-07-02)

> `skills/demo/` livré : renderer ANSI stdlib (`render.py`, dégrade en texte
> brut si `NO_COLOR`/non-TTY), scénario scripté 6 étapes couvrant les 4
> panneaux, `scripted`/`live`/`replay` dans `demo.py` + `cli.py`. 9 tests.

**But :** `python -m skills.demo.cli` → un split-screen ANSI qui montre en
direct ce que la belt décide. L'effet "wow" du README en vrai.

```
┌─ ROUTING ────────────────────┐┌─ SAVINGS (session) ─────────┐
│ task: "rename var in a.py"   ││ tokens saved   12 480       │
│ effort_classifier → LOCAL 93%││ cloud calls avoided  17     │
│ filter hit: 1 (micro-NN)     ││ cache hits           41     │
├─ MICRO-NN ───────────────────┤├─ ESCALATIONS ───────────────┤
│ binary_router  [0.91|0.09]   ││ 14:02 verification_failed   │
│ anomaly_det    normal        ││       local → cloud (glm)   │
└──────────────────────────────┘└─────────────────────────────┘
```

**Deux modes :**
1. `--live` — tail de `events.jsonl` (P0) pendant qu'un agent travaille.
2. `--scripted` — rejoue un scénario embarqué (5-6 tâches types : trivial →
   local, dur → escalade, doublon → cache hit). **C'est le mode démo salon /
   README GIF** : marche sur une machine vierge, sans LLM local installé.

- Briques réutilisées : `auto_router`, `botte_nn`, cache, P0.
- À écrire : renderer ANSI (stdlib, pas de `rich` — respecter la règle
  zéro-dépendance), scénario scripté.
- Effort : **M**. Dépend de P0 (mode live) mais `--scripted` peut sortir avant.
- Bonus : enregistrer un asciinema/GIF pour le README (voir P5e).

---

## P2 — Dashboard : terminal + live 📊 ✅ fait (2026-07-02)

> `skills/dashboard/tui.py` livré : `--tui` (une frame) et `--watch`
> (boucle, re-collecte toutes les `--interval`s, Ctrl+C pour arrêter).
> Sparklines unicode sur `trends.show()`. Réutilise le renderer ANSI de
> `demo` — un seul renderer pour les deux outils vitrine. 7 tests.

**Existant :** `skills/dashboard` génère déjà un HTML autonome timestampé
(control_loop + trends + metrics + fix). Le P7 historique est donc à moitié fait.

**À ajouter :**

| Livrable | Détail | Effort |
|----------|--------|--------|
| `--tui` | même JSON assemblé, rendu ANSI dans le terminal (sparklines unicode ▁▂▅▇ pour les trends) | S |
| `--watch` | re-rendu toutes les N s en lisant `events.jsonl` (P0) — le dashboard devient vivant | S |
| `--serve` | `http.server` stdlib qui re-génère le HTML à chaque requête (optionnel) | S |

Le HTML et le TUI consomment **le même assembleur de données** (`--json`
existant) : une seule source de vérité, deux rendus.

---

## P3 — `botte doctor` 🩺 ✅ fait (2026-07-02, extension de checkup)

**Constat :** les briques existent toutes, il manque l'assemblage UX en un seul
verbe mémorisable.

| Étape doctor | Brique existante |
|---------------|------------------|
| scan du projet | `checkup` (policy, directives, metrics, duplication, sécurité, drift) |
| scan de la machine | `llm_backends audit --fresh` (quels modèles locaux tournent ici) |
| scan des directives | `directives_audit` (déjà dans checkup) |
| optimisations proposées | `infra_advisor auto` |
| rapport | `report` / `dashboard` |

**Livrable :** `skills/doctor/` (ou sous-commande `checkup --doctor`) qui
enchaîne le tout et sort :
1. un **verdict une-ligne** (`✅ sain`, `⚠️ 3 optimisations dispo, ~N tokens/session à gagner`),
2. un rapport MD/HTML dans `.botte/reports/`,
3. le top-3 des actions classées par tokens économisés (réutiliser le framing
   coût de `metrics`/`fix`).

- Décision d'archi à trancher au moment de l'implémentation : nouvelle skill ou
  extension de `checkup` ? **Recommandation : extension de `checkup`** (une
  skill de plus = coût de contexte, et checkup fait déjà 80 % du travail).
- Effort : **S/M** — pur assemblage + mise en forme.
- C'est aussi **la** commande à mettre en avant dans le README à la place des
  3 commandes de déploiement actuelles.

> **Livré :** `checkup.cli --doctor [--fresh]` — ajoute `machine` (scan
> `llm_backends.audit`), `top_actions` (fixes de `skills.fix` classés par
> coût token estimé + drift restant, plafonné à 3) et `verdict` (une ligne).
> 5 nouveaux tests dans `test_checkup.py`, testé en conditions réelles sur ce
> repo (détecte le LM Studio local qui tourne sur cette machine).

---

## P4 — Hermes compatibility 🔌 ✅ étapes 1-2 faites, étape 3 en brouillon (2026-07-02)

> `skills/hermes_bridge/` livré (connecteur : `mcp_config()` zero-code si
> Hermes parle MCP, sinon `TOOL_SCHEMAS`+`dispatch()` façon OpenAI
> function-calling pour les 5 outils clés). `docs/integrations/hermes.md`
> livré (pourquoi + où insérer le filtre + renvoi vers `bench`). Étape 3
> (proposition upstream) : brouillon dans
> `docs/plans/2026-07-02_hermes-upstream-proposal-draft.md`, **marqué
> explicitement "ne pas publier tel quel"** — nécessite vérification contre
> le vrai repo hermes-agent et validation humaine avant tout post public.
> 9 tests.

**Existant :** `skills/hermes-second-brain/DESIGN.md` (goal layer, Qdrant,
history) + le serveur MCP `botte-llm` déjà exposé.

**Étapes :**

1. **Connecteur** `skills/hermes_bridge/` : mapper les tools botte
   (`auto_route`, `local_chat`, `fusion`, `find_skills`, `infra_tips`) vers le
   format d'outillage d'Hermes-Agent ; config d'exemple prête à copier.
   Effort : **M** (dépend du format exact d'Hermes — à vérifier sur leur repo
   au moment de l'implémentation).
2. **Doc d'intégration** : `docs/integrations/hermes.md` — pourquoi brancher la
   belt devant Hermes (chaque tâche triviale intercéptée = 0 token Hermes),
   avec chiffres mesurés par P5a (bench).
3. **Proposition upstream** : ouvrir une issue/discussion sur le repo
   hermes-agent — *"Efficiency integration: pluggable local-first routing
   belt"* — avec :
   - le bench avant/après (P5a) comme preuve,
   - le connecteur (étape 1) comme implémentation de référence,
   - zéro demande de changement invasif chez eux (pattern opt-in).

   ⚠️ **Action externe** : à rédiger ici, mais publication après relecture
   humaine (c'est une communication publique au nom du projet).

---

## P5 — Idées complémentaires (proposées en plus des 4 axes)

### P5a — `botte bench` : la preuve chiffrée 📏 ✅ fait (2026-07-02)

> `skills/bench/` livré : corpus fixe de 17 tâches (`tasks.py`), passées dans
> `auto_router.decide()` réel (0 token dépensé pour mesurer), comparées à une
> baseline documentée (tout envoyé en Tier.STANDARD). Sortie : % tokens/$ 
> économisés + % resté local. Caveat honnête documenté dans le SKILL.md (le
> corpus court favorise le local vs. de vrais prompts de prod). 13 tests.
Un benchmark reproductible : N tâches types exécutées avec et sans la belt,
sortie = tableau tokens/coût/latence. Aujourd'hui le README annonce "~65 %
(reported by users)" — un bench versionné dans le repo transforme une
affirmation en preuve. **C'est le meilleur argument pour P4-étape 3 et pour
l'adoption en général.** Effort : M.

### P5b — Session replay ("boîte noire") ⏪
`python -m skills.demo.cli --replay .botte/events.jsonl` : rejouer une vraie
session au rythme réel ou accéléré. Quasi gratuit une fois P0 + P1 faits
(même renderer). Usage : debug du routing, démos avec de vraies données, et
matière première pour l'active-learning loop. Effort : S.

### P5c — GitHub Action packagée ⚙️ ✅ déjà en place (constaté 2026-07-02)
`.github/workflows/botte-pr-checkup.yml` existe déjà et fait exactement ça :
lance `checkup --pr-comment` sur chaque PR, poste/édite un commentaire unique.
Documenté comme réutilisable par tout projet ayant déployé botte-secrète
(voir `checkup/SKILL.md` § "On pull requests"). Rien à ajouter.

### P5d — Statusline Claude Code 💡 ✅ fait (2026-07-02)
`skills/statusline/` livré : `render(project)` lit `.botte/events.jsonl`,
sort une ligne (`🧦 12,480 tok saved · 41 cache hits · 17L/3C · 2 escalated`),
ne lève jamais. CLI compatible hook `statusLine` de Claude Code (lit un JSON
sur stdin si présent). Instructions de câblage dans le SKILL.md — ne modifie
pas les settings de l'utilisateur automatiquement. 9 tests.

### P5e — Kit démo README 🎥 ✅ fait (2026-07-02, version texte)
Section "🎬 See it decide, live" ajoutée au README avec une vraie capture du
mode scripté + les 4 commandes vitrine (`demo`, `dashboard --tui`, `bench`,
`checkup --doctor`). Un GIF asciinema reste une amélioration possible plus
tard, mais la preuve texte/capture est déjà en place et 100% reproductible
(`python -m skills.demo.cli scripted`).

### P5f — Fleet view multi-projets 🗺️
`dashboard --fleet` : agréger les `.botte/` de tous les projets de la machine
en une vue (économies totales, projets non encore équipés). Transforme botte
d'outil par-repo en plateforme machine-wide. Effort : M. **À garder pour plus
tard** — dépend de P0/P2 stabilisés.

---

## 📅 Séquencement proposé

| Ordre | Item | Effort | Dépend de | Wow/effort |
|-------|------|--------|-----------|------------|
| 1 | P0 event log | S | — | fondation |
| 2 | P1 demo `--scripted` | M | — | ⭐⭐⭐ |
| 3 | P3 botte doctor | S/M | — | ⭐⭐⭐ |
| 4 | P2 dashboard `--tui` + `--watch` | S | P0 | ⭐⭐ |
| 5 | P1 demo `--live` + P5b replay | S | P0, P1 | ⭐⭐ |
| 6 | P5e kit démo README | S | P1 | ⭐⭐⭐ |
| 7 | P5a bench | M | — | ⭐⭐ (preuve) |
| 8 | P4 Hermes bridge + doc | M | P5a idéalement | ⭐⭐ |
| 9 | P4 proposition upstream | S | P4, P5a | ⭐⭐⭐ |
| 10 | P5c action GitHub, P5d statusline | S | — | ⭐ |
| 11 | P5f fleet view | M | P0, P2 | ⭐ |

**Règles transverses** (héritées du projet) : stdlib only, 0 réseau par défaut,
tout testable offline, chaque nouvelle skill passe par `nn_audit`/`checkup`
pour ne pas créer de coût de contexte non justifié.

---

## Annexe A — Prompt source amélioré

> Version retravaillée du prompt d'origine, réutilisable telle quelle :

```text
Contexte : Botte Secrète est une plateforme d'optimisation de tokens (routing
local↔cloud, micro-NN, cache, harness anti-hallucination). Le moteur marche
mais est invisible : rien ne montre ses décisions ni ses économies.

Mission : produis une roadmap complète "showcase & UX" dans un fichier
docs/plans/<date>_showcase-ux-roadmap.md, en t'appuyant d'abord sur les briques
existantes du repo (dashboard, checkup, control_loop, metrics, llm_backends,
hermes-second-brain) plutôt qu'en réinventant.

Axes imposés :
1. Demo mode interactif (CLI) : décisions de routing, économies live, sorties
   micro-NN, escalades, cache hits.
2. Dashboard : compléter le HTML existant par une version terminal et un mode
   live.
3. "botte doctor" : un seul verbe qui scanne projet + machine + directives,
   propose les optimisations et génère un rapport (assemblage des briques
   existantes).
4. Compatibilité Hermes-Agent : connecteur, doc, puis proposition
   d'intégration "efficiency" au repo hermes-agent (brouillon à faire relire
   avant publication).

Attendu en plus : tes propres idées complémentaires, un séquencement avec
efforts (S/M/L) et dépendances, et le respect des contraintes du projet
(stdlib only, offline, 0 télémétrie).
```
