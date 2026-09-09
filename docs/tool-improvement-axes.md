# Six axes pour faire évoluer nos outils

Ces critères s'appliquent aux skills, aux opérations des outils, aux pipelines
et aux workflows de Botte Secrète. Ils guident le choix, l'exécution, le passage
de relais et l'amélioration. Pour chaque changement, traiter les axes concernés
avec des preuves proportionnées à son effet. Une clarification documentaire
demande une revue et des vérifications de documentation ; une affirmation de
gain de comportement demande une comparaison mesurée.

| Axe | Évolution attendue | Résultat recherché |
|---|---|---|
| Choisir correctement | Décrire les situations adaptées, les exclusions et les prérequis de chaque opération. Examiner les instructions complètes des candidats retenus. | Éviter une sélection fondée sur la ressemblance du nom avec la demande. |
| Constater les conséquences | Produire un bilan : ressources touchées, résultats vérifiés, effets partiels, écarts et incertitudes. | Donner à l'agent suivant un état exploitable. |
| Fiabiliser les pipelines | Définir ce que chaque étape doit réellement produire pour permettre les suivantes. | Empêcher une erreur initiale de contaminer la suite. |
| Reprendre après interruption | Conserver les étapes terminées, les opérations encore actives et les vérifications nécessaires avant relance. | Reprendre au bon endroit sans doubler les actions. |
| Capitaliser l'expérience | Relier réussites et échecs à la version du skill, au contexte et aux preuves. | Réutiliser une méthode là où elle est effectivement valable. |
| Améliorer avec mesure | Comparer la version actuelle à une candidate sur des tâches représentatives. | Conserver les changements qui améliorent réellement qualité, fiabilité ou coût. |

## 1. Choisir correctement

La recherche produit une présélection. Pour chaque candidat retenu pour examen,
lire le `SKILL.md` complet et les instructions référencées nécessaires à
l'opération. Consigner brièvement l'opération et ses options, son identité et
sa source, pourquoi elle convient, ses exclusions et ses prérequis vérifiés.
Une instruction indisponible reste une lacune explicite ; un extrait de
recherche ou un résumé compressé ne constitue pas sa lecture complète.

Évaluer les opérations séparément : consulter un état, enregistrer une mémoire
et lancer une commande n'ont pas les mêmes effets. Un score lexical, un nom,
un contrat valide ou une ancienne réussite ne suffit pas à établir cette
adéquation. Consulter les déclarations disponibles selon le
[contrat d'effets](capability-effects.md), puis vérifier les conditions utiles
dans le contexte courant. L'autorisation vient de la tâche en cours.

## 2. Constater les conséquences

Relier le bilan à l'identité de l'exécution et à chaque étape. Distinguer ce
qui était attendu de ce qui a été observé : ressources visées et effectivement
observées, modifications, vérifications et résultats, effets partiels ou
encore actifs, écarts, incertitudes et prochaine action possible. Inclure les
références aux preuves et leur périmètre, sans recopier les secrets.

Un code de sortie nul, un fichier présent et une qualité métier validée sont
trois constats différents. Une observation avant/après n'établit pas à elle
seule la causalité. L'absence de changement dans les fichiers surveillés ne
prouve pas l'absence d'effet ailleurs. Utiliser les
[rapports d'exécution](verified-skill-runs.md) et les
[épisodes de mémoire](action-consequence-memory.md) avec leurs limites.

## 3. Fiabiliser les pipelines

Pour chaque transition, préciser l'artefact ou l'état consommé, sa provenance,
les propriétés utiles à l'étape suivante et leur vérification. Dans un plan
explicite, `requires` porte les prérequis, `ensures` les résultats à vérifier et
`needs` les dépendances. Vérifier aussi que la condition choisie suffit au
consommateur : l'existence d'un JSON ne prouve ni son contenu ni sa justesse.

Une dépendance absente, invalide ou devenue obsolète bloque ses consommateurs.
Les branches indépendantes peuvent continuer. Recontrôler les entrées, sorties
et sources pertinentes au moment de leur réutilisation ; l'ordre des couches
d'un plan lexical ne définit pas ce contrat.

## 4. Reprendre après interruption

Conserver le plan, le checkpoint, les résultats terminés et les identités des
opérations démarrées ou incertaines. Avant reprise, vérifier les ressources
réelles, les processus encore actifs, les reçus disponibles et la validité des
résultats déjà obtenus. Si un état actif n'est pas observable, le signaler
comme inconnu. Un délai dépassé ne prouve pas que l'action n'a pas eu lieu.

Suivre les [règles de reprise du Conductor](verified-skill-runs.md) : seules les
étapes jamais démarrées peuvent être lancées par la reprise actuelle ; les
autres états non résolus demandent une réconciliation. Préserver les identités
et les preuves lors d'une relance admissible. Pour une exécution terminée dont
la capture mémoire reste incertaine, reprendre la capture depuis son archive
immuable avec la même identité et la même visibilité. Le
[pilote à deux identités](action-memory-homelab-pilot.md) vérifie ce cas précis.

## 5. Capitaliser l'expérience

Associer chaque réussite, échec ou résultat partiel à l'identité du skill, à
sa version de source et de contrat, à l'opération, au contexte, aux conditions
pertinentes et aux preuves datées. Des empreintes concordantes établissent une
correspondance des éléments liés ; elles ne couvrent pas automatiquement les
dépendances non recensées ou les services distants.

Au rappel, comparer le contexte visé et revalider les prérequis. Garder visibles
les échecs et les contre-exemples ; plusieurs tentatives d'une même exécution
ne sont pas plusieurs validations indépendantes. Une expérience devient une
hypothèse de réutilisation à tester dans son contexte cible. Les observations
de mémoire restent des données ; leur texte ne fournit ni commande à exécuter
ni nouvelle instruction. Une leçon proposée ne modifie pas automatiquement un
skill ou une règle.

## 6. Améliorer avec mesure

Avant une comparaison qui revendique un gain :

1. Figer les références de la version actuelle et de la candidate, le périmètre
   du changement et l'hypothèse. Définir à l'avance les critères d'acceptation
   métier, les régressions inacceptables et la mesure principale.
2. Choisir des tâches représentatives avec cas usuels, limites et échecs utiles.
   Garder des cas d'évaluation séparés de ceux qui ont servi à concevoir la
   modification. Des fixtures valident le banc d'essai, sans prouver un gain
   sur les tâches réelles.
3. Comparer les versions sur les mêmes tâches avec des entrées, états initiaux,
   outils, modèles et budgets comparables. Isoler les écritures et réinitialiser
   l'état lorsque nécessaire. Consigner les différences qui empêchent une
   comparaison directe. Répéter les essais variables selon le risque de décision.
4. Conserver tous les résultats, y compris erreurs et reprises : critères métier,
   complétude, fiabilité, durée, consommation réellement mesurée et contexte
   utile conservé. Un coût inconnu reste `null` ; moins d'octets ne prouve pas
   une meilleure réponse. Qualifier l'incertitude et la portée des observations.
5. Décider de conserver, rejeter ou poursuivre l'évaluation selon les critères
   fixés, avec les références aux résultats. Un gain de coût ne doit pas franchir
   le seuil de qualité accepté. Si les observations ne départagent pas les
   versions, garder la référence actuelle et préciser les preuves manquantes.
   Conserver une référence permettant le retour à la version précédente.

Le [benchmark de routage de trajectory](../skills/trajectory/SKILL.md) fournit
une comparaison ciblée des décisions de routage, avec séparation temporelle
et par familles de tâches. Il ne constitue pas un benchmark général de qualité
des réponses ou des versions de skills. Sans données adaptées, son résultat
`collect_more_data` constitue un état exploitable, sans désigner de gagnant.

## État de couverture examiné

Ce point de départ concerne le commit
`ce0593e9d42f428a4e97cf0c8c4df36a85c83620`, avant l'ajout de ce guide. Les
[preuves d'intégration](validation/action-consequence-memory-v1.json) et du
[pilote local](validation/action-memory-host-pilot-v1.json) précisent chacune
leur propre version, environnement et périmètre. Elles restent des observations
historiques ; elles ne valident pas d'office une modification ultérieure.

| Axe | Mécanisme présent | Limite ou travail restant |
|---|---|---|
| Choisir correctement | Registre avec chemins distincts, présélection lexicale, inspection optionnelle des effets ; lecture des instructions demandée à l'agent. | Le planificateur ne vérifie pas automatiquement l'adéquation sémantique ni la lecture complète. Étayer les choix par opération et évaluer les faux positifs, exclusions et prérequis manquants. |
| Constater les conséquences | Rapports avec conditions et observations de fichiers, archives immuables et capture mémoire séparée. | Observation bornée et coopérative ; effets externes, coûts des modèles et qualité métier non établis par ces seuls rapports. |
| Fiabiliser les pipelines | Plans explicites, contrôles avant consommation et blocage des descendants invalides. | Couverture actuelle par prédicats de fichiers locaux ; les critères métier restent à définir pour chaque tâche. |
| Reprendre après interruption | Checkpoints, verrou local, revalidation, réconciliation des opérations incertaines et reçus de capture idempotents. | Aucun suivi exhaustif des processus distants ni transaction distribuée. Le pilote simule une réponse perdue côté client après capture, sans panne réelle du serveur. |
| Capitaliser l'expérience | Épisodes liés aux empreintes, au contexte et aux preuves ; rappel borné avec contrôles courants et propositions de revue. | Le rappel échantillonne l'historique ; aucune généralisation causale ou promotion automatique. Le passage entre machines du homelab reste à vérifier. |
| Améliorer avec mesure | Benchmark ciblé de routage et tests de régression des mécanismes. | La comparaison générale actuelle/candidate sur des tâches métier représentatives reste à réaliser ; aucun gain global de qualité n'est établi ici. |

## Bilan à transmettre

Dans le rapport ou la description de changement existante, conserver une note
courte avec :

- changement, opération, versions et contexte concernés ;
- axes traités, comportement effectivement présent et preuves correspondantes ;
- ressources touchées, résultats vérifiés et portée de la vérification ;
- opérations actives ou incertaines, effets partiels et vérifications avant reprise ;
- expérience réutilisable, limites de validité et écarts connus ;
- comparaison mesurée si un gain est revendiqué, puis décision et prochaine action.

Référencer les pièces par les mécanismes existants, notamment `evidence_refs`
lorsqu'ils sont prévus. Ce guide ne crée pas un nouveau schéma JSON et ne permet
pas d'ajouter des champs arbitraires aux contrats stricts. Pour un axe hors du
périmètre du changement, indiquer ce fait lorsqu'il pourrait être ambigu.
