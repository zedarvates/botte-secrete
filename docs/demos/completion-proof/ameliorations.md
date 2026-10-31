# Avancement et suite proposée

## 1. Vérifier la preuve, pas seulement sa présence

**Réalisé en v1** : validateur distinct, empreinte de référence externe au rapport,
existence et empreinte des pièces, lien avec les fichiers de code et de test,
résultat enregistré, tests adversariaux et démonstration rejouée. Voir le
[contrat et ses limites](../../../skills/completion_proof/VERIFICATION.md).
L'exécuteur doit rester de confiance ; un reçu cohérent n'est pas une signature
indépendante. Un exécuteur générique reste à construire.

Le périmètre initial était : ajouter un validateur distinct du détecteur déclaratif A11. Définir une racine de
preuves et refuser les références absentes, les chemins qui en sortent et les
empreintes non concordantes. Une empreinte seule ne prouve pas un test réussi :
associer résultat, commande autorisée, sortie, version du code et identifiant
d'exécution. Ne jamais exécuter une commande fournie par un rapport non fiable.

Critère : preuve absente, fichier altéré ou résultat provenant d'une autre
version donnent un statut explicite différent de « vérifié ». Ajouter les
contre-exemples correspondants au parcours public.

## 2. Permettre un contrôle bloquant explicite

**Réalisé** : `--verify --strict`, codes de sortie documentés, tests de processus
et démonstration d'une clôture conditionnelle. Seule une preuve vérifiée autorise
la suite. La chaîne qui clôture les tâches doit respecter ce code ; aucune
intégration globale ou application tierce n'est activée automatiquement.

Conserver le mode rapport actuel. Proposer un mode strict opt-in pour la CI ou
la clôture d'une tâche, basé sur le validateur, avec des codes distincts pour
preuve invalide, preuve manquante et erreur de lecture. En cas d'incertitude,
ne pas annoncer « vérifié ».

Critère : une preuve fictive empêche la validation en mode strict, tandis que le
mode rapport reste compatible. Pas de blocage généralisé activé par défaut.

## 3. Rendre le résultat plus clair

**Réalisé pour la CLI et la démonstration** : messages français/anglais, cause et
prochaine action, portée du contrôle, comptes lorsqu'ils sont disponibles, et
messages réels consultables dans la page. JSON et codes stricts inchangés.
La traduction de toute la présentation et une intégration au tableau de bord
restent possibles ensuite.

Afficher « annoncé », « preuve manquante », « test en échec » et « vérifié sur
ces tests ». Donner accès à la preuve, à sa date et aux cas couverts. Montrer
une comparaison avant/après et une version anglaise du parcours.

Critère : le lecteur comprend qui a exécuté chaque étape et ce qui reste inconnu.

## 4. Passer à un scénario issu d'un vrai correctif

**Réalisé sur le nouveau vérificateur de cette proposition** : test unittest
réellement ignoré, ancien code extrait d'un commit public, même reçu comparé
avant/après et test de non-régression. Voir le [correctif réel](real-fix.md).
Il ne s'agit pas d'un incident en production ni d'un agent autonome.

Choisir un petit défaut public de Botte, conserver le test de non-régression
et le correctif, puis enregistrer une exécution reproductible. Un essai avec
un agent réel serait une expérience séparée, avec modèle, coût et intervention
humaine explicités.

Critère : un tiers rejoue le défaut puis le correctif sur la même base sans
accéder à des dépôts privés, à une clé ou à une infrastructure personnelle.

## 5. Mesurer l'utilité

**Premier corpus synthétique réalisé** : 20 scénarios étiquetés, matrice de
confusion, cas par cas et trois limites conservées dans le résultat global.
Voir le [bilan daté](evaluation/20260913T173606016150Z/README.md).
Ce corpus construit en connaissant le code n'est ni indépendant ni représentatif
de la production ; une validation sur de vrais rapports reste à conduire.

Rejouer : `python -m skills.completion_proof.evaluate`. Le résultat est écrit dans
un nouveau sous-dossier de `.botte-cache/completion-evaluation/`. La commande
mesure les résultats, sans changer le vérificateur et sans bloquer sur un score.

Sur un corpus annoté de rapports synthétiques puis de cas publics : mesurer
fausses alertes, déclarations non prouvées manquées et coût du contrôle. Le
nombre d'anomalies détectées ne doit pas être présenté comme un nombre de bugs
évités ; une réduction de reprises exige une comparaison spécifique.
