# Revue hebdomadaire du portefeuille

Date de revue : `YYYY-MM-DD`  
Responsable : `zedarvates`

## 1. Vérifier les changements

- relever les derniers commits, pull requests, issues et échecs CI ;
- noter uniquement les changements réellement observés ;
- créer un issue séparé pour toute régression fonctionnelle ;
- ne pas confondre message de commit et validation réussie.

## 2. Contrôler les trois chantiers principaux

| Emplacement | Projet | Résultat attendu cette semaine | Blocage | Décision |
|---|---|---|---|---|
| Produit cœur |  |  |  |  |
| Revenus/livraison |  |  |  |  |
| Recherche/publication |  |  |  |  |

Un quatrième chantier ne devient principal qu'après suspension ou clôture de l'un des trois.

## 3. Mettre à jour le registre

Pour chaque projet touché :

- vérifier `status`, `priority` et la prochaine action ;
- confirmer que le dépôt ou la source déclarée reste la source de vérité ;
- marquer toute classification incertaine `needs-review` ;
- supprimer du registre tout détail qui ressemble à un secret ou à un chemin privé.

## 4. Vérifier les risques

| Risque | Projet | Gravité | Preuve | Action |
|---|---|---|---|---|
| Régression fonctionnelle |  |  |  |  |
| Secret/exposition |  |  |  |  |
| Dette de tests |  |  |  |  |
| Publication non reproductible |  |  |  |  |
| Dépendance abandonnée |  |  |  |  |

## 5. Préparer les actions

Chaque action doit avoir :

- un résultat observable ;
- une branche ou un espace de travail identifié ;
- des contrôles de validation ;
- une limite de portée ;
- une règle claire de confirmation avant production ou publication.

## 6. Clôturer la revue

Créer un snapshot daté seulement si des faits ont changé. Les décisions durables vont dans `DECISIONS.md`; les détails temporaires restent dans le snapshot.
