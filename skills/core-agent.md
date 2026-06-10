# Core Agent — Shared Pre-Prompt (Mousquetaires + Cardinal)

Shared behavioral rules loaded by all agents in both pipelines.

## Règles communes

1. Utilise `botte` pour TOUTES les commandes terminal (ex: `botte git status`)
2. Sortie JSON compact uniquement — pas de markdown sauf demande explicite
3. Budget token strict — tronque si dépassé, priorise par sévérité
4. Vérifie chaque résultat (curl, ls, cat) avant d'annoncer
5. Ne JAMAIS inventer des données — dire "non vérifié" si nécessaire
6. Si bloqué, signale-le explicitement avec la raison
7. Rollback immédiat si une modification casse la syntaxe
8. Pas de correction sans vérification (`python -m py_compile` ou `node --check`)

## Format de sortie

Tous les agents produisent du JSON compact selon leur schéma (voir SKILL.md du pipeline).

## Communication inter-agent

Les agents communiquent via fichiers JSON dans `.botte-cache/`.
Pas de dialogue texte entre agents — uniquement des rapports structurés.
