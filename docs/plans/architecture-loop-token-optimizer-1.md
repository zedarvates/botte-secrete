---
goal: Réduire le coût des boucles rétroactives de Botte Secrète par orchestration déterministe, routage local et apprentissage mesuré
version: 1.0
date_created: 2026-07-13
last_updated: 2026-07-13
owner: Botte Secrète
status: 'In progress'
tags: [architecture, feature, loops, token-optimization, local-first]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Ce plan ajoute un contrôleur unifié pour les boucles rétroactives des agents de
développement. Il réutilise les modules existants de Botte Secrète, mesure les
économies réelles et interdit les répétitions sans progrès. CogniARC et
ARC-AGI-3 sont hors périmètre. Needle est évalué uniquement comme routeur
d'outils local optionnel.

## 1. Requirements & Constraints

- **REQ-001**: Chaque boucle possède un `loop_id`, un budget total, un nombre maximal d'itérations et une condition d'arrêt explicite.
- **REQ-002**: Le contrôleur évalue chaque itération comme `progress`, `stalled`, `regressed` ou `solved`.
- **REQ-003**: Une action ayant produit la même signature d'échec sans modification d'entrée ne peut pas être répétée.
- **REQ-004**: Le cache exact, les empreintes et les règles déterministes sont consultés avant tout modèle.
- **REQ-005**: Seuls le delta actif et les références indispensables sont chargés lors d'une nouvelle itération.
- **REQ-006**: La vérification intermédiaire cible uniquement les sections modifiées et à risque; une vérification globale reste obligatoire avant succès final.
- **REQ-007**: Les prédicteurs Belt 2.0 conseillent le contrôleur et doivent pouvoir s'abstenir; ils ne remplacent pas les garde-fous.
- **REQ-008**: Needle reçoit au maximum dix outils préfiltrés et une entrée inférieure ou égale à 1 024 tokens.
- **REQ-009**: Toute sortie d'un modèle de routage est validée contre les outils admissibles et leurs schémas avant exécution.
- **REQ-010**: Les économies sont calculées à partir des tokens effectivement évités, jamais à partir d'un pourcentage codé en dur.
- **REQ-011**: Le cœur reste utilisable sans Needle, sans Qdrant, sans GPU et sans réseau.
- **REQ-012**: Aucun code, dataset, protocole métier ou package CogniARC n'est importé.
- **SEC-001**: Un modèle ne peut jamais autoriser seul une mutation, une commande externe, un accès réseau ou une escalade cloud.
- **SEC-002**: Les arguments d'outil sont validés par allowlist et schéma; les arguments non déclarés sont rejetés.
- **SEC-003**: Les prompts, sorties et erreurs susceptibles de contenir des secrets sont expurgés avant journalisation.
- **CON-001**: Python 3.10+ et bibliothèque standard uniquement pour le cœur.
- **CON-002**: Toute lecture ou écriture texte utilise `encoding="utf-8"`.
- **CON-003**: Les états JSON utilisent `skills.atomic_json.write_json`.
- **CON-004**: Les rapports inter-modules utilisent des dictionnaires JSON compacts.
- **GUD-001**: Les règles déterministes précèdent la sélection lexicale, Needle, les micro-NN, le LLM local et le cloud, dans cet ordre.
- **GUD-002**: Chaque phase doit conserver la suite pytest, les 51 tests E2E et le pré-commit au vert.
- **PAT-001**: Les intégrations optionnelles suivent le pattern d'abstention et de dégradation gracieuse de `skills.auto_router.nn_belt2`.

## 2. Implementation Steps

### Implementation Phase 1 — Contrat, métriques et référence

- GOAL-001: Définir le contrat de boucle et établir une mesure reproductible avant optimisation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Créer `skills/loop_optimizer/models.py` avec les dataclasses `LoopRequest`, `LoopState`, `LoopDecision`, `LoopOutcome` et les enums `ProgressState`, `LoopAction`, `StopReason`. | ✅ | 2026-07-14 |
| TASK-002 | Définir dans `LoopRequest` les champs obligatoires `loop_id`, `goal`, `max_iterations`, `max_total_tokens`, `max_cloud_tokens`, `criticality` et `allowed_tools`. | ✅ | 2026-07-14 |
| TASK-003 | Créer `skills/loop_optimizer/ledger.py`; écrire un JSONL append-only contenant les tokens de contexte, exécution et vérification par itération. | ✅ | 2026-07-14 |
| TASK-004 | Créer `skills/loop_optimizer/baseline.py`; simuler une boucle complète sans optimisation et produire `iterations`, `tokens_total`, `cloud_tokens`, `agents_run` et `success`. | ✅ | 2026-07-14 |
| TASK-005 | Ajouter `skills/loop_optimizer/test_models.py` et `test_ledger.py` avec validation des budgets négatifs, identifiants vides, JSON corrompu et Unicode. | ✅ | 2026-07-14 |

Critères de fin de phase : le même scénario produit une baseline déterministe et un ledger relisible sans modèle ni réseau.

### Implementation Phase 2 — Arrêt, progression et mémoire des échecs

- GOAL-002: Éliminer les itérations inutiles avant tout appel de modèle.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | Créer `skills/loop_optimizer/progress.py`; comparer tests réussis, erreurs, empreintes, fichiers modifiés et nouvelle information pour retourner un `ProgressState`. | ✅ | 2026-07-14 |
| TASK-007 | Créer `skills/loop_optimizer/failures.py`; calculer `sha256(error_type + normalized_message + changed_fingerprints + action)` et conserver les 500 dernières signatures. | ✅ | 2026-07-14 |
| TASK-008 | Créer `skills/loop_optimizer/guards.py`; implémenter les arrêts `solved`, `budget_exhausted`, `iteration_limit`, `no_change`, `repeated_failure` et `regression`. | ✅ | 2026-07-14 |
| TASK-009 | Exiger deux itérations `stalled` consécutives avant arrêt, sauf empreinte strictement identique et signature d'échec répétée. | ✅ | 2026-07-14 |
| TASK-010 | Ajouter des tests prouvant qu'une boucle répétée s'arrête avant tout appel de routeur et qu'une nouvelle modification réautorise une tentative. | ✅ | 2026-07-14 |

Critères de fin de phase : aucun scénario identique ne peut consommer deux fois le même budget après le même échec.

### Implementation Phase 3 — Contexte et vérification différentiels

- GOAL-003: Réutiliser les briques existantes au lieu de créer de nouveaux compresseurs.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Extraire `WindowManager` de `skills/context_windows/cli.py` vers `skills/context_windows/windows.py`; maintenir les imports existants pour compatibilité. | ✅ | 2026-07-14 |
| TASK-012 | Remplacer le résumé de delta fondé sur des ensembles par un delta ordonné identifiant fichiers, sections, lignes et risques. | ✅ | 2026-07-14 |
| TASK-013 | Extraire `DeltaVerifier` de `skills/harness_delta/cli.py` vers `skills/harness_delta/verifier.py`; rendre ses snapshots persistants et atomiques. | ✅ | 2026-07-14 |
| TASK-014 | Ajouter `LoopContextBuilder` dans `skills/loop_optimizer/context.py`; charger fenêtre active, delta, erreurs non résolues et références explicitement requises. | ✅ | 2026-07-14 |
| TASK-015 | Ajouter un plafond dur `max_context_tokens`; appliquer d'abord pruning déterministe, puis `context_pruning_hint` uniquement si la limite reste dépassée. | ✅ | 2026-07-14 |
| TASK-016 | Ajouter une vérification globale finale obligatoire même lorsque les vérifications delta intermédiaires réussissent. | ✅ | 2026-07-14 |

Critères de fin de phase : un fichier inchangé ne figure pas dans le contexte d'une itération intermédiaire et est néanmoins couvert par la validation finale appropriée.

### Implementation Phase 4 — Contrôleur et routage des actions

- GOAL-004: Orchestrer cache, règles, agents, outils et modèles dans un ordre de coût strict.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Créer `skills/loop_optimizer/controller.py` avec `LoopController.decide(state)` et `LoopController.record(outcome)`. | ✅ | 2026-07-14 |
| TASK-018 | Implémenter l'échelle `guards → exact cache → lexical tool filter → optional Needle → Belt 2.0 → local LLM → cloud`. | ✅ | 2026-07-14 |
| TASK-019 | Connecter `skills.response_cache.ResponseCache` avec une clé incluant objectif, delta, outil, schéma, modèle et limites de sortie. | ✅ | 2026-07-14 |
| TASK-020 | Utiliser `skip_agent_hint` uniquement après les règles de domaine et de cache; interdire le skip pour `criticality >= 0.8` ou confiance inférieure au seuil. | ✅ | 2026-07-14 |
| TASK-021 | Utiliser `cloud_escalation_hint` comme avis; `AutoRouter` conserve la décision finale de budget et de disponibilité. | ✅ | 2026-07-14 |
| TASK-022 | Ajouter `skills/loop_optimizer/cli.py` avec `run`, `explain`, `stats`, `replay` et sortie JSON compacte. | ✅ | 2026-07-14 |

Critères de fin de phase : `explain` indique quelle marche a décidé, lesquelles ont été évitées et le coût estimé de la décision.

### Implementation Phase 5 — Expérience Needle optionnelle

- GOAL-005: Évaluer Needle sans l'ajouter aux dépendances du cœur.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-023 | Créer `skills/tool_router/base.py` avec le protocole `route(query, tools) -> ToolRouteResult` et une implémentation lexicale stdlib. | ✅ | 2026-07-14 |
| TASK-024 | Créer `skills/tool_router/needle_adapter.py`; importer `needle_rs` uniquement dans le constructeur et retourner une abstention si le package ou les poids manquent. | ✅ | 2026-07-14 |
| TASK-025 | Limiter l'adaptateur à dix outils et rejeter les entrées estimées au-delà de 1 024 tokens avant inférence. | ✅ | 2026-07-14 |
| TASK-026 | Valider nom d'outil, arguments requis, types primitifs et propriétés supplémentaires avant de retourner une route exécutable. | ✅ | 2026-07-14 |
| TASK-028 | Créer `skills/tool_router/benchmark.py`; comparer lexical, Needle et routeur existant sur exactitude outil, exactitude arguments, abstention, latence et mémoire. | ✅ | 2026-07-14 |
| TASK-027 | Créer `skills/tool_router/eval_dataset.jsonl` avec au moins 200 exemples Botte en français et en anglais, répartis entre routes valides, ambiguïtés et abstentions. | ✅ | 2026-07-14 |
| TASK-029 | N'activer Needle automatiquement que si exactitude outil ≥ 95%, arguments valides ≥ 98%, faux routage dangereux = 0 et p95 inférieur au LLM local. | ✅ | 2026-07-14 |

Critères de fin de phase : Needle reste désactivé si un seuil échoue; aucune installation n'est requise pour exécuter Botte normalement.

### Implementation Phase 6 — Politique apprise sur données Botte

- GOAL-006: Apprendre les décisions de boucle uniquement après collecte de résultats réels vérifiés.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-030 | Collecter au moins 2 000 transitions Botte vérifiées avant tout entraînement de politique. | | |
| TASK-031 | Créer les features `iteration_ratio`, `budget_ratio`, `fingerprint_match`, `failure_repeat`, `progress_score`, `cache_history`, `verification_state`, `criticality` et `local_fail_rate`. | | |
| TASK-032 | Entraîner d'abord un classificateur compact produisant `stop`, `retry_local`, `change_tool`, `verify`, `ask_local`, `escalate`; ne pas entraîner un générateur de texte. | | |
| TASK-033 | Réserver 20% des trajectoires par période temporelle pour éviter la fuite entre variantes proches d'une même boucle. | | |
| TASK-034 | Exiger une amélioration ≥ 10% des tokens moyens sans baisse du taux de réussite avant activation. | | |
| TASK-035 | Conserver une abstention et un fallback déterministe pour chaque classe de sortie. | | |

Critères de fin de phase : la politique apprise bat le contrôleur déterministe sur le holdout sans augmenter les régressions ni les escalades injustifiées.

### Implementation Phase 7 — Intégration, observabilité et déploiement progressif

- GOAL-007: Rendre le système observable, désactivable et sûr à déployer.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-036 | Ajouter les outils MCP `loop_decide`, `loop_record`, `loop_explain` et `loop_stats` dans `skills/llm_mcp/server.py`; conserver le chargement paresseux. | ✅ | 2026-07-14 |
| TASK-037 | Ajouter les événements `loop_start`, `loop_decision`, `loop_stop` et `loop_saving` dans `skills/events/events.py`. | ✅ | 2026-07-14 |
| TASK-038 | Ajouter au dashboard les métriques tokens par boucle, itérations évitées, agents skippés, répétitions bloquées, cache hits et escalades cloud. | ✅ | 2026-07-14 |
| TASK-039 | Ajouter les variables `BOTTE_LOOP_OPTIMIZER=0|shadow|1` et `BOTTE_NEEDLE_ROUTER=0|shadow|1`; valeur par défaut `shadow` pour le contrôleur et `0` pour Needle. | ✅ | 2026-07-14 |
| TASK-040 | En mode `shadow`, journaliser la décision proposée sans modifier le pipeline réel. | ✅ | 2026-07-14 |
| TASK-041 | Activer progressivement à 10%, 50%, puis 100% des boucles après au moins 100 scénarios par palier sans régression. | ✅ | 2026-07-14 |

Critères de fin de phase : désactiver les deux fonctionnalités restaure immédiatement le comportement antérieur sans migration de données.

## 3. Alternatives

- **ALT-001**: Fine-tuner immédiatement Needle pour toutes les décisions. Rejeté car le checkpoint INT4 ciblé n'est pas un checkpoint d'entraînement et Needle ne gère pas les retours d'outils ni les boucles multi-étapes.
- **ALT-002**: Utiliser un LLM local pour chaque décision de boucle. Rejeté car les arrêts, budgets, empreintes et répétitions sont déterministes et ne doivent consommer aucun token.
- **ALT-003**: Créer un micro-NN par nouvelle décision. Rejeté comme architecture principale car la fragmentation complique la calibration; les prédicteurs existants restent des avis spécialisés.
- **ALT-004**: Partager du code ou des datasets avec CogniARC. Rejeté explicitement; les objectifs, observations, actions et métriques des deux projets sont distincts.
- **ALT-005**: Remplacer les modules P48-P55 existants. Rejeté; le plan extrait, corrige et orchestre les briques existantes.

## 4. Dependencies

- **DEP-001**: `skills.atomic_json` pour les états persistants.
- **DEP-002**: `skills.response_cache` pour les résultats exacts.
- **DEP-003**: `skills.context_windows` pour les fenêtres actives et deltas.
- **DEP-004**: `skills.harness_delta` pour les vérifications intermédiaires.
- **DEP-005**: `skills.auto_router.nn_belt2` et `skills.auto_router.router` pour les avis et escalades.
- **DEP-006**: `skills.events` pour la télémétrie locale.
- **DEP-007**: `needle-rs` est une dépendance facultative limitée à la phase 5; aucune dépendance runtime obligatoire n'est ajoutée.

## 5. Files

- **FILE-001**: `skills/loop_optimizer/__init__.py` — API publique.
- **FILE-002**: `skills/loop_optimizer/models.py` — contrats typés.
- **FILE-003**: `skills/loop_optimizer/controller.py` — orchestration centrale.
- **FILE-004**: `skills/loop_optimizer/guards.py` — budgets et arrêts.
- **FILE-005**: `skills/loop_optimizer/progress.py` — mesure du progrès.
- **FILE-006**: `skills/loop_optimizer/failures.py` — mémoire des échecs.
- **FILE-007**: `skills/loop_optimizer/context.py` — contexte minimal.
- **FILE-008**: `skills/loop_optimizer/ledger.py` — trajectoires et métriques.
- **FILE-009**: `skills/loop_optimizer/baseline.py` — comparaison avant/après.
- **FILE-010**: `skills/loop_optimizer/cli.py` — commandes utilisateur.
- **FILE-011**: `skills/tool_router/base.py` — interface et routeur lexical.
- **FILE-012**: `skills/tool_router/needle_adapter.py` — intégration optionnelle.
- **FILE-013**: `skills/tool_router/benchmark.py` — évaluation locale.
- **FILE-014**: `skills/context_windows/windows.py` — logique extraite de la CLI.
- **FILE-015**: `skills/harness_delta/verifier.py` — logique extraite de la CLI.
- **FILE-016**: `skills/llm_mcp/server.py` — outils MCP paresseux.
- **FILE-017**: `skills/events/events.py` — événements de boucle.

## 6. Testing

- **TEST-001**: Tests unitaires des validations de `LoopRequest` et des transitions d'état.
- **TEST-002**: Tests de propriété vérifiant qu'aucun budget ne devient négatif et qu'une boucle atteint toujours un état terminal.
- **TEST-003**: Tests de répétition prouvant que la même action après le même échec est bloquée.
- **TEST-004**: Tests de contexte prouvant qu'un contenu inchangé n'est pas rechargé.
- **TEST-005**: Tests du harness prouvant qu'une modification risquée est vérifiée même si son empreinte globale est proche.
- **TEST-006**: Tests de sécurité des sorties Needle inconnues, arguments supplémentaires, types incorrects et JSON malformé.
- **TEST-007**: Tests de fallback sans package Needle, sans poids, sans modèle local et sans clé cloud.
- **TEST-008**: Benchmark déterministe d'au moins 20 scénarios comparant baseline et contrôleur optimisé.
- **TEST-009**: Seuil d'acceptation initial : ≥30% de tokens en moins à réussite égale; les objectifs supérieurs sont mesurés et non présumés.
- **TEST-010**: Exécution obligatoire de `python -m pytest --rootdir=. -q`, `python skills/test_e2e.py`, `python scripts/pre-commit-check.py --fast` et `python -m skills.checkup.cli .` à chaque phase.

## 7. Risks & Assumptions

- **RISK-001**: Un skip erroné peut masquer une régression; les tâches critiques interdisent le skip appris.
- **RISK-002**: Une optimisation mesurée sur des scénarios trop proches surévalue les gains; le holdout est séparé temporellement.
- **RISK-003**: Needle est entraîné en anglais; le dataset d'évaluation doit inclure une majorité de requêtes françaises représentatives.
- **RISK-004**: Le format Needle INT4 nécessite son runtime spécifique et ne permet pas un fine-tuning direct avec Transformers.
- **RISK-005**: Une télémétrie trop détaillée peut recréer un coût de contexte; les journaux restent compacts et ne sont chargés que sur demande.
- **RISK-006**: Des garde-fous trop agressifs peuvent arrêter une boucle qui aurait progressé; le mode shadow précède toute activation.
- **ASSUMPTION-001**: Les modules existants restent les sources de vérité pour cache, contexte, harness et routage.
- **ASSUMPTION-002**: Les trajectoires Botte fournissent suffisamment de résultats vérifiés pour entraîner une politique après la phase 5.
- **ASSUMPTION-003**: CogniARC reste un projet entièrement séparé et n'est utilisé que comme inspiration conceptuelle humaine.

## 8. Related Specifications / Further Reading

- [Botte Secrète AGENTS.md](../../AGENTS.md)
- [Politique locale Botte Secrète](../../.botte/policy.md)
- [Needle INT4 pour needle-rs](https://huggingface.co/Abdalrahman/needle-rs-safetensors)
- [Needle amont entraînable](https://huggingface.co/Cactus-Compute/needle)
- [CogniARC — référence conceptuelle séparée](https://github.com/zedarvates/cogniarc)
