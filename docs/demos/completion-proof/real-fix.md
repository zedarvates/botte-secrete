# Un vrai correctif : les tests tous ignorés

Le nouveau vérificateur de Botte pouvait déclarer une preuve vérifiée alors que
le reçu indiquait que tous les tests avaient été ignorés. `unittest` considère
une exécution sans erreurs comme réussie même lorsqu'elle n'exécute aucun test.
Le vérificateur contrôlait erreurs et échecs, mais ne tenait pas compte de `skipped`.

La reproduction lance réellement un test décoré `unittest.skip`, capture son
résultat et son journal, puis présente **le même reçu** aux deux implémentations.
La version avant provient directement du commit public
`4cffa4b941979ef84518b12c2b5d139fb07a8550`, sans modification pour fabriquer le défaut.

| Contrôle | Avant | Après |
|---|---|---|
| Reçu : un test découvert, un ignoré | Accepté | Refusé |
| Même test de non-régression | Échec | Réussite |
| Tests ignorés avec nombre invalide | Non contrôlés | Refusés |
| Un test exécuté et un ignoré | Portée imprécise | Comptes distingués |

## Rejouer

Depuis un clone Git contenant le commit de référence :

```text
python docs/demos/completion-proof/real_fix.py
```

Le script écrit une exécution datée et `real-fix.html` dans
`.botte-cache/real-completion-fix/`. `--output` permet de choisir un autre dossier.
Il ne télécharge rien et ne modifie pas le dépôt. Un clone trop superficiel ou
une archive sans historique ne permet pas d'extraire l'ancienne version : le
script s'arrête alors explicitement.

La [présentation enregistrée](real-fix-evidence/real-fix.html) s'ouvre localement
après téléchargement. Les pièces datées sont dans [real-fix-evidence](real-fix-evidence/).

## Limites

Ce bug a été trouvé dans le vérificateur développé dans cette proposition ; il
ne documente pas un incident de production. La reproduction et la correction
sont pilotées par nous, sans agent autonome ni modèle externe.

Les anciens reçus v1 peuvent omettre `skipped` : l'absence conserve la valeur
zéro pour compatibilité. Les nouveaux exécuteurs doivent enregistrer ce nombre.
La confiance dans l'exécuteur et la portée limitée aux fichiers/tests déclarés
restent nécessaires. Ce correctif ne résout pas les faux négatifs d'un exécuteur
qui ne fournit pas des comptes fidèles.
