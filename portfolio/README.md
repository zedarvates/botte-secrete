# Portfolio Cockpit

Ce dossier initialise le pilotage commun des projets sans déplacer leur source de vérité.

## Architecture retenue

- **Botte Secrète** porte la gouvernance, le registre, les contrôles et la mémoire partagée.
- **Kanboard Neo** est le candidat pour l'interface humaine : priorités, files de travail, échéances et activité.
- **Chaque dépôt ou source locale déclarée** reste la source de vérité de son propre code et de ses documents.
- `projects.json` est l'index machine-readable qui relie ces éléments.

```text
Sources de vérité (GitHub / local privé / externe)
                         |
                         v
                portfolio/projects.json
                         |
             +-----------+-----------+
             |                       |
             v                       v
    Botte Memory Hub          Kanboard Neo
  contexte gouverné         vue humaine/tâches
             |                       |
             +-----------+-----------+
                         v
              branche -> tests -> PR
```

## Règles de sécurité

Le registre ne doit jamais contenir :

- secrets, jetons, mots de passe ou clés privées ;
- données de joueurs, clients ou utilisateurs ;
- chemins locaux absolus ;
- adresses d'infrastructure privées non nécessaires ;
- contenu propriétaire qui n'est pas indispensable au pilotage.

Les projets locaux confidentiels sont représentés par un identifiant et une description minimale. Une vue publique devra être générée par assainissement explicite, jamais par copie directe de ce dossier.

## Flux de travail

1. Observer les changements récents et leurs preuves.
2. Mettre à jour le statut provisoire dans `projects.json`.
3. Convertir la prochaine action en tâche Kanboard.
4. Charger dans Memory Hub seulement le contexte utile au projet concerné.
5. Travailler sur une branche dédiée.
6. Exécuter les contrôles pertinents.
7. Ouvrir une pull request en brouillon.
8. Exiger une confirmation explicite pour production, publication, DNS, données ou opération destructive.
9. Mettre à jour le snapshot et les décisions après fusion.

## Limite de travail en cours

Le portefeuille cible au maximum trois chantiers principaux simultanés :

1. un produit cœur ;
2. un chantier revenus ou livraison ;
3. un chantier recherche/publication.

Les autres projets restent en `maintenance`, `incubation`, `needs-review` ou `archived`. Cette limite est une politique de pilotage proposée et peut être revue par le propriétaire.

## Statuts

| Statut | Sens |
|---|---|
| `active` | travail courant avec prochaine action définie |
| `maintenance` | stable ou secondaire, corrections ciblées |
| `incubation` | idée/prototype sans engagement de livraison |
| `publication` | preuves, manuscrit et archives en préparation |
| `needs-review` | rôle ou état réel à auditer |
| `archived` | conservé, sans travail prévu |

Les priorités et statuts initiaux sont **provisoires**. Ils ont été construits à partir de l'inventaire GitHub et du contexte de travail connu, puis doivent être confirmés pendant les revues.

## Fichiers

- `projects.json` — registre complet et provisoire.
- `DECISIONS.md` — décisions d'architecture et de gouvernance.
- `WEEKLY_REVIEW.md` — procédure de revue.
- `snapshots/2026-08-06.md` — première photographie des changements observés.

## Étapes d'intégration suivantes

1. Ajouter une compétence Botte `portfolio_sync` en lecture seule qui compare GitHub au registre et produit un diff JSON.
2. Importer les entrées utiles dans Memory Hub au statut `proposal`, jamais directement `promoted`.
3. Auditer l'API et le modèle de Kanboard Neo avant toute synchronisation en écriture.
4. Déployer progressivement `AGENTS.md`, `STATUS.md` et `DECISIONS.md` dans les projets actifs.
5. Générer plus tard une vue publique assainie, séparée du registre privé.

Cette première étape n'ajoute aucun accès à la production, aucun secret et aucune automatisation destructive.
