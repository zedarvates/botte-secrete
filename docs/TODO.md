# 🧦 Botte Secrète — TODO (300 tâches max)

> Généré le 2026-07-03, à partir de l'usage réel du projet pendant nos
> sessions (implémentation du showcase & UX roadmap, lectures de code,
> exécutions de tests, appels d'outils MCP) — pas une liste théorique.
> Chaque section "🔎 observé" cite un fait concret vu pendant une session,
> pas une supposition. Cases à cocher pour suivre l'avancement.
>
> Priorité suggérée : 🔴 haute · 🟡 moyenne · ⚪ basse/nice-to-have.

---

## 1. Nouveaux axes de réduction — découverts en session (prioritaire) 🔴

> Ces items viennent directement de motifs observés dans NOS échanges, pas
> d'une liste générique. Ce sont les pistes les plus concrètes du fichier.

- [ ] 🔴 **Auditer le coût du catalogue MCP hôte lui-même** — chaque tour de
      cette session recevait la liste complète des serveurs MCP "en attente de
      connexion" (Blender, godot-ai, Desktop Commander, pdf-viewer…) avec
      description longue, même quand aucun n'est utilisé. C'est exactement le
      problème que `llm_mcp` a résolu pour son propre serveur (lazy tool
      loading, mesuré par `context_profiler`) — mais côté hôte, personne ne le
      mesure. Étendre `context_profiler` pour estimer ce coût "hors botte".
- [ ] 🔴 **`context_profiler --host`** — nouveau mode qui simule/estime le
      prefix ajouté par l'environnement d'exécution (system-reminder, listes de
      skills, serveurs MCP déférés) séparément du CLAUDE.md du projet, pour
      distinguer "ce que botte contrôle" de "ce que l'hôte impose".
- [ ] 🔴 **Skill catalog lazy-loading, façon `find_skills`, appliqué à la
      liste de skills de l'hôte** — la session a vu défiler une liste de
      >400 noms de skills à chaque tour (Anthropic + plugins tiers). Documenter
      le pattern (au lieu de tout lister, chercher par mot-clé) comme
      recommandation dans `infra_advisor`/`checkup` pour les projets qui
      exposent beaucoup de skills à un agent.
- [ ] 🟡 **`rtk` : supprimer le nag répété "No hook installed"** — observé sur
      *chaque* appel bash de la session (`rtk read`, `rtk git ...`) : le même
      avertissement est réimprimé à chaque fois, gonflant chaque sortie lue par
      l'agent. Proposer à l'amont RTK (ou wrapper localement) : n'afficher
      qu'une fois par session, ou après `rtk init -g`, silence total.
- [ ] 🟡 **Godot/Blender-style "instructions bundle" — mesurer le coût texte
      des instructions MCP tierces** — `godot-ai`/`Blender` livrent chacun un
      bloc d'instructions de plusieurs dizaines de lignes, chargé même hors
      contexte jeu vidéo/3D. Ajouter un item dans `infra_advisor` : détecter
      les serveurs MCP configurés mais non pertinents pour le type de projet
      (`skill_project_optimizer` type detection) et suggérer leur retrait du
      `.mcp.json` local.
- [ ] 🟡 **Réduire le bruit `git` répété (warnings CRLF/LF)** — observé : 30+
      lignes `warning: ... LF will be replaced by CRLF` à chaque `git add` sur
      ce repo (Windows). Chaque ligne est relue par l'agent = tokens perdus
      sans information utile après la première fois. Ajouter `.gitattributes`
      cohérent au repo, ou `core.safecrlf=false` documenté, pour couper le bruit.
- [ ] 🟡 **`run_tests.py --changed`** — observé : cette session a relancé la
      suite complète (40+ sous-process) après quasi chaque ajout de skill,
      alors que 1 seul module changeait. Détecter les fichiers modifiés
      (`git diff --name-only`) et ne lancer que les suites correspondantes +
      un résumé compact, pas la sortie complète de chaque sous-process.
- [ ] 🟡 **Compacter la sortie de `run_tests.py`** — actuellement chaque
      suite imprime son propre `PASS`/`FAIL` par cas ; sur une suite verte,
      l'agent n'a besoin que du total. Ajouter `--quiet` : une ligne par suite
      sauf échec (détail complet uniquement pour les suites en échec).
- [ ] 🔴 **Prefix caching / réutilisation KV-cache pour les modèles locaux**
      — le `local_harness` relance un prompt complet à chaque appel ; pour LM
      Studio/Ollama qui supportent le cache de préfixe, structurer les prompts
      système pour maximiser la réutilisation (system prompt stable en tête,
      contenu variable en fin) réduit le temps ET le "coût" local (moins de
      re-calcul token par token même si non facturé).
- [ ] 🟡 **Déduplication inter-SKILL.md** — plusieurs `SKILL.md` répètent des
      phrases similaires ("pure stdlib", "0 cloud tokens", tableau
      "Related:"). Si plusieurs skills sont chargés ensemble dans une session,
      ce boilerplate se répète. `docs_steward` pourrait extraire un fragment
      commun (`_shared/footer.md`) inclus par référence plutôt que dupliqué.
- [ ] 🟡 **Audit des relectures de fichiers dans une session** — observé :
      plusieurs `Read` du même fichier après un `Edit` réussi dans cette
      session, alors que l'outil garantit déjà l'état post-édition. Documenter
      la règle dans `AGENTS.md`/`CLAUDE.md` du projet : ne jamais relire un
      fichier juste édité sauf besoin explicite (déjà en partie fait, à
      renforcer avec un exemple concret tiré de cette session).
- [ ] ⚪ **Mesurer le coût des `<system-reminder>` de mémoire auto** — le
      bloc "auto memory" + `MEMORY.md` est injecté à chaque session. Une fois
      `MEMORY.md` volumineux (des dizaines d'entrées), ajouter un mode
      `context_profiler --memory` qui alerte si ce fichier dépasse un seuil.
- [ ] 🟡 **Batching des appels d'outils indépendants** — observé : plusieurs
      tours de cette session auraient pu paralléliser 2-3 `Read`/`Bash`
      indépendants au lieu de les enchaîner séquentiellement (chaque aller-
      retour ajoute un tour de contexte). Ajouter une checklist courte dans
      `AGENTS.md` : "avant d'enchaîner des lectures indépendantes, les
      grouper".
- [ ] ⚪ **Cache de résultats `checkup`/`bench` entre tours rapprochés** — si
      l'agent relance `checkup .` deux fois dans la même session à quelques
      minutes d'écart sans changement de fichiers, resservir depuis
      `.botte-cache/` (déjà présent pour d'autres scans) plutôt que rescanner.
- [ ] 🟡 **`events` : ajouter un kind `tool_call` pour tracer le coût agent
      lui-même** — actuellement `events.jsonl` trace les décisions du belt
      mais pas les tours d'agent (Read/Edit/Bash) qui, eux aussi, consomment
      du contexte. Un log optionnel `tool_call` (nom, taille approx. de la
      sortie) permettrait à `context_profiler` de corréler "activité belt" et
      "activité agent" dans le même dashboard.

---

## 2. Belt / routing — affiner la décision locale ↔ cloud 🔴

- [ ] 🔴 Entraîner `effort_classifier` sur un corpus de prompts *réels* (pas
      seulement synthétiques) — le bench (`skills/bench`) a montré que des
      prompts courts biaisent vers LOCAL ; collecter un vrai corpus depuis
      `control-ledger.jsonl` pour ré-entraîner.
- [ ] 🔴 Ajouter un signal de longueur de *contexte accumulé* (pas seulement
      le prompt courant) à `effort.py` — une tâche courte dans une session
      longue n'a pas le même coût qu'isolée.
- [ ] 🟡 Détecter les tâches répétitives (rename, format, lint) via un cache
      de *forme* de prompt (pas seulement le texte exact) pour élargir les
      hits de `cache.ProjectCache`.
- [ ] 🟡 Ajouter un mode `auto_router.dry_run_session(events)` qui rejoue une
      session `events.jsonl` et propose un diff de seuils (ce que
      `control_loop.adapt()` fait déjà, mais visualisable via `demo replay`).
- [ ] 🟡 Exposer un seuil de confiance minimal configurable par projet
      (`.botte/policy.md`) pour le NN belt, au lieu d'une constante globale.
- [ ] ⚪ Ajouter une 5ᵉ voie de fusion : "batch" — regrouper plusieurs
      micro-tâches indépendantes en un seul appel local pour amortir l'overhead
      fixe par requête (`_THROUGHPUT` overhead dans `cost_estimator`).
- [ ] 🟡 `nn_belt.local_vs_cloud_hint` : ajouter un mode "explain" qui retourne
      les features qui ont fait pencher la décision (déjà en germe dans
      `_belt_ctx`), affichable dans `demo` MICRO-NN.
- [ ] 🟡 Étendre `auto_router.decide()` pour accepter un budget de latence en
      plus du budget $ — certaines tâches locales sont lentes (`_THROUGHPUT`
      montre LOCAL à 35 tok/s) et un budget temps pourrait forcer le cloud
      même si $ le permet.
- [ ] ⚪ `providers.py` : ajouter un mode "dry" qui simule un fournisseur
      cloud sans clé API pour tester `fusion`/`cascade` en CI sans réseau.
- [ ] 🟡 Ajouter la détection de "boucle d'escalade" — si le même type de
      tâche escalade en cloud plus de N fois dans une session, proposer une
      action correctrice immédiate (pas seulement via `control_loop` différé).
- [ ] ⚪ Étudier un mode "speculative local" — lancer le local en parallèle du
      cloud pour les tâches à la frontière CHEAP/STANDARD, garder le premier
      qui répond avec une confiance suffisante (complexité vs gain à évaluer).
- [ ] 🟡 `effort.py` : pondérer différemment "long prompt mais très
      répétitif" (ex: gros diff mais mécanique) vs "long prompt et complexe" —
      actuellement la longueur seule pousse vers un tier plus élevé.
- [ ] ⚪ Ajouter des tests de régression sur `effort.py` avec le corpus de
      `skills/bench/tasks.py` comme jeu de vérité versionné.
- [ ] 🟡 `fusion.cascade` : logger dans `events` la raison précise de
      l'escalade (score de confiance, pas juste "low-confidence").
- [ ] ⚪ Explorer un routing par *sous-tâche* pour les prompts composites
      (ex: "refactor + écris les tests") plutôt qu'une décision unique.
- [ ] 🟡 Ajouter un `--explain` à `auto_router.cli route` qui imprime le détail
      des signaux ayant mené à la décision (déjà dans `EffortEstimate.reasons`,
      pas assez visible en CLI).

---

## 3. Harness local — fiabilité et honnêteté du modèle local 🔴

- [ ] 🔴 Étendre `local_harness` avec un mode de vérification spécifique au
      code (exécution réelle en sandbox) en plus de la vérification
      structurelle actuelle.
- [ ] 🔴 Mesurer le taux réel d'escalade "verification_failed" sur des
      sessions longues et ajuster `MIN_SAMPLES`/`STEP` de `control_loop` en
      fonction (actuellement des constantes fixes).
- [ ] 🟡 Ajouter une bibliothèque de "prompts pièges" (le local ment/halluciné)
      versionnée dans `local_harness/test_bench.py` pour éviter les
      régressions de fiabilité au fil des mises à jour de modèle local.
- [ ] 🟡 `local_harness` : logger un `nn_out`-style event quand la
      vérification échoue, avec la raison, pour alimenter `demo`/`dashboard`.
- [ ] ⚪ Support multi-modèles locaux en parallèle (vote local, pas seulement
      cascade local→cloud) pour les tâches à la frontière FREE/LOCAL.
- [ ] 🟡 Ajouter un mode `--strict` au harness qui refuse silencieusement de
      répondre plutôt que de risquer une hallucination sur les tâches
      "critical_fix"/sécurité — forcer l'escalade cloud pour cette classe.
- [ ] ⚪ Étudier l'ajout d'un mini-modèle de classification "réponse
      halluciné vs correcte" entraîné sur l'historique des escalades
      `verification_failed` (nouveau micro-NN candidat, à qualifier par
      `nn_audit` dès sa création pour éviter le piège "synthetic + wired").
- [ ] 🟡 Documenter dans `local_harness/SKILL.md` les modèles locaux testés
      et leur taux d'escalade mesuré (transparence, matière pour `bench`).

---

## 4. `events` / `demo` / `dashboard` — approfondir la vitrine 🟡

- [ ] 🟡 `events` : ajouter un export CSV/Parquet pour analyse hors-ligne
      (pandas côté utilisateur, sans que botte en dépende).
- [ ] 🟡 `demo --live` : ajouter un filtre par kind (`--only route,escalate`)
      pour les sessions bruyantes.
- [ ] ⚪ `demo` : mode "diff" qui compare deux sessions replay côte à côte
      (avant/après un changement de seuils `control_loop`).
- [ ] 🟡 `dashboard --watch` : ajouter une alerte sonore/visuelle (bell ANSI)
      quand une escalade survient pendant l'observation live.
- [ ] ⚪ `dashboard --tui` : ajouter un panneau "coût cumulé $ session" en
      plus des tokens, utile pour les utilisateurs qui payent par usage cloud.
- [ ] 🟡 `events` : ajouter une commande `events stats` qui résume sans tout
      imprimer (comme `control_loop analyze` mais sur le log live, pas le
      ledger historique).
- [ ] ⚪ `demo scripted` : ajouter 2-3 scénarios alternatifs sélectionnables
      (`--scenario web-frontend`, `--scenario security-audit`) pour coller au
      type de projet démontré.
- [ ] 🟡 `fleet` : ajouter un tri (`--sort tokens_saved|loc|fixes`) sur la
      sortie `--fleet` pour les machines avec beaucoup de projets enregistrés.
- [ ] ⚪ `fleet aggregate` : ajouter un mode `--since <date>` en combinant
      avec `trends` (nécessite que `trends.snapshot` tourne périodiquement
      sur chaque projet du fleet).
- [ ] 🟡 `statusline` : ajouter une variante compacte (`--compact`, juste le
      chiffre de tokens économisés) pour les barres de statut à espace réduit.
- [ ] ⚪ Un mode `demo --export-gif` qui pilote `asciinema`/`agg` si présents
      sur la machine (optionnel, jamais une dépendance dure) pour finaliser
      P5e (le repo a le texte, pas encore le GIF binaire).
- [ ] 🟡 `bench` : ajouter un second corpus "long/réaliste" (prompts avec
      stack traces et diffs complets) en complément du corpus court actuel,
      pour donner un chiffre "plancher" ET un chiffre "réaliste" cote à cote.
- [ ] 🟡 `bench --compare <ancien_run.json>` : comparer deux exécutions dans
      le temps (régression de routing après une mise à jour de seuils).
- [ ] ⚪ Publier les résultats de `bench` en CI (artifact, pas un badge auto —
      éviter de mentir sur un chiffre non vérifié à chaque run).
- [ ] 🟡 `checkup --doctor` : ajouter la détection "aucun local model + bench
      jamais lancé" comme item de drift à part entière (aujourd'hui seulement
      "aucun backend" est signalé, pas "aucune preuve chiffrée").

---

## 5. Hermes / intégrations externes 🟡

- [ ] 🔴 Vérifier `hermes_bridge` contre le vrai repo hermes-agent dès qu'un
      accès est possible ; corriger `TOOL_SCHEMAS` si le format diffère.
- [ ] 🟡 Ajouter un connecteur générique "LangChain tool" (format différent
      d'OpenAI function-calling) en plus du bridge Hermes, si la demande existe.
- [ ] 🟡 Ajouter un connecteur "AutoGen"/"CrewAI" si un besoin utilisateur
      se confirme — ne pas construire avant qu'un cas d'usage réel existe.
- [ ] ⚪ Documenter un connecteur générique "n8n"/"Zapier webhook" pour
      exposer `auto_route` à des workflows no-code.
- [ ] 🟡 `hermes_bridge.dispatch` : ajouter une limite de taille de réponse
      configurable (certains frameworks tiers ont des limites de payload).
- [ ] 🟡 Poster la proposition upstream Hermes une fois relue par un humain
      (voir `docs/plans/2026-07-02_hermes-upstream-proposal-draft.md`).
- [ ] ⚪ Ajouter un exemple d'intégration MCP côté Cursor/Windsurf dans
      `docs/integrations/` (au-delà de Claude Code, déjà documenté).

---

## 6. Micro-NN — grounding et qualité 🟡

- [ ] 🔴 Regrounder `binary_router` sur données réelles (actuellement flagué
      "synthetic + wired" par `nn_audit` selon le dernier `checkup --doctor`).
      Le ledger distingue désormais observations et verdicts explicites via
      `feedback_id`/`route_feedback`; toutes les routes comparables alimentent
      maintenant le mode shadow, sans auto-label. Activation bloquée jusqu'à
      2 000 verdicts vérifiés.
- [ ] 🔴 Regrounder `effort_classifier` — même statut à risque.
- [ ] 🔴 Regrounder ou retirer `anomaly_detector` — vérifier s'il a de vrais
      consommateurs en production avant de décider grounding vs suppression.
- [ ] 🟡 Ajouter un pipeline d'entraînement reproductible (`training/`) qui
      documente la source des données pour chaque micro-NN, pas seulement le
      format des poids.
- [ ] 🟡 `nn_audit` : ajouter un historique (tendance du % grounded dans le
      temps, via `trends`) plutôt qu'un instantané seul.
- [ ] ⚪ Étudier la distillation d'un micro-NN à partir des décisions
      `control-ledger.jsonl` accumulées (apprentissage semi-supervisé local).
- [ ] 🟡 Documenter dans chaque `SKILL.md` de micro-NN la taille du modèle
      et le budget mémoire (utile pour les machines contraintes, cf. les
      travaux Hailo/edge déjà présents dans le repo).

---

## 7. Sécurité — élargir la couverture 🟡

- [x] ✅ Éliminer les auto-détections des signatures malveillantes citées dans
      les chaînes, docstrings et commentaires Python sans masquer les appels réels.
- [ ] 🔴 Étendre `fallow_like` (taint analysis) aux frameworks web courants
      (Flask/FastAPI/Express patterns) au-delà des primitives génériques.
- [ ] 🟡 `security_scanner` : ajouter la détection de secrets dans les
      commits historiques (pas seulement le working tree actuel).
- [ ] 🟡 Ajouter un scan de dépendances (SBOM léger, stdlib uniquement —
      parser `requirements.txt`/`Cargo.toml`/`package.json` pour CVE connues
      via une base locale, pas d'appel réseau par défaut).
- [ ] ⚪ `checkup --doctor` : ajouter le résultat du scan dépendances au
      verdict et au top 3 actions si des CVE critiques sont trouvées.
- [ ] 🟡 Documenter une politique de disclosure pour les faux positifs du
      scanner malveillant (actuellement `_MALICIOUS_HIGH_SIGNAL` est une
      liste fixe — permettre un allowlist projet dans `.botte/policy.md`).
- [ ] ⚪ Ajouter un mode `security_scanner --diff` qui ne scanne que les
      fichiers modifiés depuis la dernière analyse (perf sur gros repos).
- [ ] 🟡 Étendre `cwe_kb` avec plus d'entrées CWE couvrant les patterns
      spécifiques aux agents IA (prompt injection, exfiltration via outils).
- [ ] ⚪ Ajouter un test de non-régression : `hermes_bridge`/MCP tools ne
      doivent jamais exécuter du code arbitraire venant d'un prompt sans
      validation (audit ciblé du dispatcher).

---

## 8. Tests et CI 🟡

- [x] ✅ Marquer le câblage MCP machine-local comme non applicable dans le
      runner PR éphémère, sans supprimer l'alerte du checkup local.
- [ ] 🟡 `run_tests.py` : paralléliser les suites indépendantes (actuellement
      séquentiel — 40+ suites, gain de temps mur significatif possible).
- [ ] 🟡 Ajouter un mode `--fail-fast` pour le développement itératif.
- [ ] ⚪ Générer un rapport de couverture agrégé (par module) même sans
      dépendance `coverage.py` lourde — un comptage de lignes exécutées stdlib.
- [ ] 🟡 Ajouter un test de non-régression README : vérifier que chaque
      commande citée dans le README s'exécute réellement sans erreur (script
      dédié, exécuté en CI, pour éviter la dérive doc/code déjà corrigée une
      fois avec `demo replay`).
- [ ] 🟡 Étendre `ci.yml` pour lancer `bench` et publier le delta de savings
      en commentaire de PR (comme `checkup --pr-comment`).
- [ ] ⚪ Ajouter un job CI "cold machine" (sans backend local) pour vérifier
      que tous les fallbacks cloud/absence gracieuse fonctionnent.
- [ ] 🟡 Ajouter des tests de charge légers sur `events.py` (rotation à 5 Mo)
      avec un vrai gros volume simulé, pas seulement le seuil abaissé en test.
- [ ] ⚪ Vérifier la compatibilité multi-OS (le repo tourne actuellement
      testé principalement sous Windows dans nos sessions — ajouter un job
      Linux/macOS explicite si pas déjà couvert par `ci.yml`).

---

## 9. Documentation et onboarding ⚪

- [ ] 🟡 Ajouter un GIF/asciinema réel du `demo scripted` (P5e, version
      texte déjà livrée — reste la version animée binaire).
- [ ] 🟡 Créer un `docs/GETTING_STARTED.md` condensé (le README fait 400+
      lignes — un chemin "5 minutes" séparé du reste).
- [ ] ⚪ Traduire le README en français (le projet et les plans sont
      bilingues, le README principal est 100% anglais).
- [ ] 🟡 Documenter la structure `.botte/` complète en un seul endroit (le
      README "System Impact" liste les items mais pas leur schéma JSON).
- [ ] ⚪ Ajouter un schéma des events (`docs/schemas/events-schema.md`,
      cohérent avec `docs/schemas/report-schemas.md` existant).
- [ ] 🟡 `docs_steward` : passer sur ce TODO.md périodiquement pour détecter
      les tâches devenues obsolètes (auto-review, pas de suppression
      silencieuse).
- [ ] ⚪ Ajouter des captures d'écran du `dashboard` HTML dans le README (le
      TUI a une capture texte, le HTML n'a aucun aperçu visuel).
- [ ] 🟡 Documenter un guide de contribution "ajouter un micro-NN sans
      tomber dans le piège synthetic+wired" (leçon tirée de l'historique
      `nn_audit` du projet).

---

## 10. Infra / hardware ⚪

- [ ] 🟡 Étendre `infra_advisor` avec des profils GPU AMD/Intel (actuellement
      centré NVIDIA/Apple Silicon dans la plupart des heuristiques).
- [ ] ⚪ Ajouter un mode `infra_advisor --budget <€>` qui recommande un
      matériel local à acheter pour un budget donné plutôt qu'un simple
      diagnostic de l'existant.
- [ ] 🟡 Documenter des profils de modèles quantifiés (GGUF Q4/Q8) adaptés
      par tranche de RAM/VRAM, avec les compromis qualité/vitesse mesurés.
- [ ] ⚪ Ajouter un mode cluster réel (au-delà de `skills/cluster` actuel) qui
      détecte plusieurs machines sur le même réseau local et répartit les
      tâches selon leur charge (extension de `llm_backends` scan réseau).
- [ ] 🟡 `hailo-vision`/edge : documenter des cas d'usage concrets déjà
      couverts par le pipeline (le fichier existe, l'usage réel reste à
      illustrer avec un exemple bout-en-bout).

---

## 11. Nettoyage et dette technique ⚪

- [ ] 🔴 Traiter les 89 fixes détectés par `skills.fix` sur ce repo (80
      duplication + 9 dead_code, vus lors du smoke test `checkup --doctor`).
- [ ] 🟡 Committer `.botte/policy.md` sur ce repo lui-même (signalé "not
      committed" par `checkup` durant cette session).
- [ ] 🟡 Réduire le always-on CLAUDE.md/AGENTS.md de ce repo si possible
      (16 860 tok/session mesuré par `checkup` pendant cette session).
- [ ] ⚪ Revisiter `fix-report.json` à la racine (fichier orphelin observé
      dans `ls` — vérifier s'il est encore généré/consommé quelque part).
- [x] 🟡 Vérifier la cohérence des badges de version (`v1.9.0rc1`) avec le
      `CHANGELOG.md` — processus de bump à documenter/automatiser.
- [ ] ⚪ Ajouter un script de nettoyage `.botte-cache/`/`.pytest_cache/`
      pour les machines de développement (déjà partiellement dans `cache`,
      pas exposé en CLI top-niveau).

---

## 12. API et surface MCP 🟡

- [ ] 🟡 Réduire encore la surface toujours-chargée du serveur `llm_mcp` —
      mesurer si le "core set" actuel (post lazy-loading) peut être réduit
      davantage sans nuire à la découvrabilité (`find_tool`).
- [ ] 🟡 Ajouter un outil MCP `bench_run` pour lancer `skills.bench` depuis
      un client MCP sans passer par le CLI.
- [ ] 🟡 Ajouter un outil MCP `doctor` (actuellement seulement `auto_audit` —
      exposer `checkup --doctor` directement, machine scan inclus).
- [ ] ⚪ Ajouter un outil MCP `fleet_status` pour interroger l'agrégat fleet
      sans sortir en CLI.
- [ ] 🟡 Documenter le contrat de compatibilité du serveur MCP (versioning
      des noms d'outils) pour ne pas casser `hermes_bridge`/clients externes
      lors de futures évolutions.
- [ ] ⚪ Ajouter un mode `--dry-run` global au serveur MCP qui journalise les
      appels sans les exécuter (utile pour auditer un client tiers non fiable
      avant de l'autoriser en prod).

---

## 13. Idées plus exploratoires — à qualifier avant de coder ⚪

- [ ] ⚪ Étudier un mode "diff-only context" pour les agents longue-durée :
      au lieu de renvoyer le fichier entier après un edit, ne renvoyer que le
      diff appliqué (déjà en partie la philosophie de l'outil `Edit`, à
      vérifier si les skills du repo respectent ce principe).
- [ ] ⚪ Étudier l'intégration d'un cache sémantique (embeddings locaux, pas
      cloud) pour détecter des prompts *similaires* mais pas identiques,
      au-delà du cache exact actuel (`skills/cache`).
- [ ] ⚪ Étudier un mode "compression de contexte" spécifique aux gros
      fichiers de log analysés par `checkup`/`security_scanner` — résumer
      avant de faire remonter à l'agent, pas juste tronquer.
- [ ] ⚪ Étudier la possibilité d'un plugin navigateur/VS Code qui affiche le
      `statusline` en overlay, au-delà du terminal.
- [ ] ⚪ Étudier un système de "budget de session" configurable
      (`.botte/policy.md`) qui bloque/avertit avant de dépasser un nombre de
      tokens cloud pour la session en cours, pas seulement le budget
      quotidien déjà géré par `Budget`.
- [ ] ⚪ Étudier l'ajout d'un mode d'auto-évaluation périodique : le projet
      qui audite sa propre dérive de conventions au fil des sessions
      (extension de `docs_steward`, versionnée dans le temps via `trends`).

---

## Comment utiliser ce fichier

- Cocher au fur et à mesure (`- [x]`), ne pas supprimer les tâches terminées
  — l'historique de ce qui a été fait est aussi utile que ce qui reste.
- Chaque tâche qui débouche sur du travail réel devrait produire son propre
  plan dans `docs/plans/<date>_<sujet>.md`, comme
  `2026-07-02_showcase-ux-roadmap.md` — ce fichier est un inventaire, pas un
  plan d'exécution détaillé.
- Les items 🔴 de la section 1 sont les plus directement actionnables et les
  moins spéculatifs : ils viennent d'un fait observé, pas d'une idée générique.
