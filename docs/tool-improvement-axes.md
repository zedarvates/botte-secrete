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

Synthèse du 2026-09-13 : mécanismes examinés au commit
`099efb9f203fd1666cb6707d34d4fb5a2be9152d`, après le point de départ
`ce0593e9d42f428a4e97cf0c8c4df36a85c83620`. Les
[preuves d'intégration](validation/action-consequence-memory-v1.json), du
[pilote local](validation/action-memory-host-pilot-v1.json) et de sélection
ci-dessous conservent chacune leur version, leur environnement et leur
périmètre. Un résultat historique ne valide pas d'office le commit examiné.

| Axe | Mécanisme présent | Limite ou travail restant |
|---|---|---|
| Choisir correctement | La [revue locale](skill-selection-review.md) charge les `SKILL.md` complets dans une limite globale de 64 Kio, conserve chemins, sous-ensemble et ordre, puis distingue sélection, abstention et indisponibilité. | Avis consultatif. Les ressources référencées restent à lire par l'agent ; la présélection lexicale peut manquer un candidat. Le modèle CPU testé échoue aux six cas exigeant l'abstention. |
| Constater les conséquences | Rapports de fichiers et archives existants ; le [bilan CPU](validation/skill-selection-cpu-execution-v1.json) relie 24 observations vérifiées aux ressources touchées, appels terminés, serveur arrêté, échecs, jetons et durées mesurés. | Observation bornée. Aucune opération sélectionnée n'a été exécutée ; qualité métier, énergie, coût monétaire et effets externes restent non mesurés. |
| Fiabiliser les pipelines | Plans explicites et blocage des descendants invalides ; le [banc de sélection](skill-selection-acceptance.md) vérifie empreintes et observations du checkpoint avant consommation, puis recalcule les scores depuis les chemins et états de revue. | Un résultat complet peut rester refusé. Les critères métier propres aux opérations et l'authenticité du runtime ne sont pas établis par ces contrôles locaux. |
| Reprendre après interruption | Checkpoints, verrou local et revalidation ; seules les opérations jamais démarrées peuvent repartir. Une capture incertaine se reprend avec la même requête conservée et la même identité. | Réconcilier les appels démarrés ou incertains avant toute suite. Aucun suivi exhaustif des processus distants ni transaction distribuée ; la perte de réponse du pilote reste simulée côté client. |
| Capitaliser l'expérience | Épisodes existants ; [export du bilan de sélection](validation/skill-selection-cpu-memory-request-v1.json) lié aux versions, contexte et preuves, puis [revue du rappel](validation/skill-selection-memory-review-v1.json) qui conserve les sept échecs et signale les sources modifiées. | L'export est une requête, pas un reçu d'ingestion ni un épisode d'exécution. Le rappel est un échantillon ; plusieurs bilans du même essai ne sont pas des validations indépendantes. Le transport entre machines reste à vérifier. |
| Améliorer avec mesure | Comparaison CPU de deux versions figées sur douze situations synthétiques, avec résultats complets et [évaluation rétrospective](validation/skill-selection-cpu-assessment-v1.json). | Sélection exacte avec revue disponible : 2/12 → 5/12 ; abstention correcte : 0/6 → 0/6 ; jetons de prompt : 1 423 → 4 199. Runtime non qualifié. Une évaluation indépendante sur les tâches cibles et les coûts reste nécessaire. |

L'essai réel compare la référence `6651335` à la candidate `8f2bd6e`, avec
Qwen2.5-0.5B-Instruct Q8_0 et llama.cpp b10809. Les ajouts ultérieurs évaluent ou
rappellent ses preuves sans produire de nouveaux appels modèle. La politique
d'acceptation a été écrite après observation des échecs ; cette évaluation est
rétrospective. La CI vérifie les mécanismes et leurs régressions, sans qualifier
le modèle pour les tâches réelles.

## Reprendre à partir de cette synthèse

- **Essai CPU terminé :** conserver ses 24 observations et son refus de
  qualification. Pour examiner ces résultats, utiliser l'évaluation hors ligne
  du [guide d'acceptation](skill-selection-acceptance.md), sans rejouer l'essai.
  Une autre hypothèse demande une candidate distincte, figée, et un nouveau
  protocole ; une qualification demande des cas cibles évalués séparément des
  cas de développement.
- **Mémoire vérifiée localement :** la preuve HTTP utilise deux identités sur
  une seule machine. L'export conservé ne prouve aucune ingestion dans un
  service configuré. Pour vérifier le passage entre machines, reprendre le
  [pilote existant](action-memory-homelab-pilot.md) avec service, identités,
  transport et révisions effectivement disponibles.
- **Réutilisation à examiner :** la revue enregistrée compare les sources de
  `f01d212` à la candidate mesurée `8f2bd6e` et signale leur différence. Ce
  constat ne diagnostique pas une régression du finder. Recontrôler les sources
  du checkout visé, le runtime et les prérequis de la tâche ; garder visibles
  les échecs historiques et les limites du rappel.

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
