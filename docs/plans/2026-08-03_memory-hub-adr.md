# ADR-014: Botte Memory Hub — mémoire d'équipe gouvernée

**Status:** Proposed
**Date:** 2026-08-03
**Deciders:** Botte Secrete maintainers

## Contexte

TencentDB Agent Memory démontre quatre actifs réutilisables (Chat Memory,
Skill, LLM-Wiki, CodeGraph) avec gouvernance, portée et routage par agent.
Botte a déjà les briques : `AutoMemory`, `docs/wiki/`, SKILL.md, MCP local.
Manquent : la gouvernance (visibilité, provenance, cycle de vie, partage
explicite entre projets/agents), un stockage isolé par projet, et un flux
contrôlé proposition → revue → promotion.

## Décision

Créer un module `skills/memory_hub/` qui étend `AutoMemory` avec :

1. **`MemoryEntry` enrichi** : `project_id`, `asset_type`, `visibility`,
   `status`, `source_ref`, `source_digest`, `expires_at`, `sensitivity`, puis
   provenance typée (`source_type`, identifiant/URI, run, date, confiance et
   classe de confiance) en v2.
2. **Stockage SQLite cloisonné** par projet, avec migration et écriture
   atomique (stdlib, pas de dépendance).
3. **Flux de cycle de vie** : proposal → review_active → promoted →
   expired / obsoleted. Forcer statut `proposed` par défaut.
4. **Cinq outils MCP** : search_hub, context_bundle, propose_memory,
   promote_memory, forget_memory.
5. **Tests** : isolement inter-projets, expiration, refus d'accès,
   suppression, provenance, cycle complet.
6. **Quarantaine v2** : les observations repo/web/tool/agent/generated sont
   stockées séparément, exclues du contexte normal, non exécutables et non
   promouvables. Les enregistrements v1 sans provenance migrent en quarantaine.

## Options considérées

### Option A (retenue) — Botte Memory Hub v1

| Dimension | Évaluation |
|---|---|
| Complexité | Moyenne (module unique, SQLite stdlib) |
| Dépendances | 0 nouvelle (stdlib + events existant) |
| Intégration MCP | 5 nouvelles primitives, compatible `llm_mcp/server.py` |
| Migration | Rétrocompatible : mémoire globale `~/.botte/memory/` lue en fallback |
| Tests | 1 nouveau fichier, isolement par `tmp_path` |

### Option B — Installer TencentDB Agent Memory

| Dimension | Évaluation |
|---|---|
| Complexité | Très élevée (3 services Docker, LLM endpoints, web panel) |
| Dépendances | Docker, deux groupes de modèles, code Python additif |
| CodeGraph | Priorise HTTPS publics, pas de test avec dépôts locaux/dirty |
| Stockage | Cloud-first, pas de chemin stdio local garanti |
| **Rejetée** car incompatible avec aucun conteneur, budget zéro cloud,
politique local-first de Botte, et arbres de travail non propres.

### Option C — Fonctionnalités incrémentales sur AutoMemory existant

| Dimension | Évaluation |
|---|---|
| Complexité | Faible |
| Portée | Aucun cloisonnement inter-projet, aucune gouvernance exploitable, pas de cycle de vie traçable |
| Périmètre | Nécessite de toute façon une migration SQLite ; aussi coûteux que A à terme |
| **Rejetée** car repousser la gouvernance à v2 coûte plus que la faire maintenant. |

## Conséquences

- **Plus facile** : gouvernance traçable, isolation inter-projets, expiration,
  provenance externalisable.
- **Plus dur** : l'ancien `MemoryBank` global n'est plus le chemin par défaut.
- **À revisiter** : le graphe de code (CodeGraph) est un chantier séparé,
  dépendant de `skills/structured_output` et `skills/knowledge_graph` en P1.

## Plan d'exécution

1. `memory_hub/schema.py` — dataclasses + SQLite DDL, `MemoryEntry` v2
2. `memory_hub/store.py` — `MemoryStore` : CRUD, search, lifecycle, ACL,
   expiration pruning
3. `memory_hub/mcp.py` — outils MCP search, context_bundle, propose,
   promote, forget
4. `memory_hub/test_memory_hub.py` — 8+ scénarios, isolement tmp_path
5. Raccord : ajouter `memory_hub` à la découverte de skills et au CLIP
   principal si pertinent

## Pourquoi maintenant

- L'état concurrent modifie 79 fichiers déjà ; le moment est bon pour une
  branche ciblée avec zéro régression.
- Tencent confirme le besoin ; le coût d'ajouter la gouvernance maintenant
  est minimal comparé à une migration ultérieure.
