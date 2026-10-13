# Contrat RSI enregistré

Ce contrat couvre uniquement l'observateur RSI de cette branche. Il ne remplace
pas les anciens contrats d'autorité, de bail, de revue indépendante ou de sortie
sûre : leurs modules ne sont pas présents ici et leur restauration reste hors
de cette correction. Aucune promotion, fusion, publication ou exécution de mission
n'est autorisée par un résultat vert de ce contrat. Ces opérations conservent
leurs autorisations propriétaire et leurs preuves distinctes.

## Règles source

RSI observe ne modifie ni fichier, ni route, ni outil, ni politique, ni modèle et ne fournit aucune commande de promotion.

La lecture RSI est bornée à 5 MiB plus un octet sentinelle ; une source absente, illisible, invalide ou partielle reste explicitement signalée.

Les arêtes RSI expriment une adjacence observée, jamais une causalité prouvée ; les mesures absentes restent null et la provenance absente reste unknown.

## Vérification

Le moteur `skills/directives_audit/rules.py` et sa CLI sont restaurés sans
modification depuis `e121ea16cbd5a772ddb485414928c0938eace2d5` (PR #103).
L'audit est en lecture seule et n'exécute pas de probe :

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python -m skills.directives_audit.rules_cli audit . --json
python scripts/check_committed_rules.py
python -m skills.directives_audit.test_rules
python -m skills.rsi_graph.test_runner
```

`last_verified` est un reçu de revue sémantique, pas une preuve d'exécution.
Le rapport `botte.rules-audit/v1` et son fingerprint portent sur les règles
inscrites, pas sur l'intégralité du dépôt. La CI bloque un manifeste absent,
une règle critique retirée, une erreur ou un avertissement ; elle exécute ensuite
les probes revus dans la matrice Python. La syntaxe est contrôlée sans importer
les modules. La CI extrait et vérifie le SHA source exact de la PR, sans accepter
le commit de fusion synthétique comme substitut. Une preuve provenant d'un autre
SHA ne débloque jamais cette branche. Une vérification périmée ou une frontière
non couverte reste BLOCKED/DRIFT pour sa portée propre.
