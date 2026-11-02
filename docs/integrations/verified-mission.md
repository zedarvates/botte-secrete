# Mission vérifiable et revue réellement terminée

Le contrôle facultatif `botte.verified-mission/v1` compose le vérificateur de
preuves existant. Il ne change ni les reçus de tests v1, ni les contrats fermés
Kanboard/Odin. Le coordinateur peut conserver le chemin et l'empreinte de ce
contrat comme pièce jointe du contrat existant ; il doit vérifier la compatibilité
avant tout raccordement automatique. Cette livraison n'active aucun service.

```bash
python -m skills.cli completion-proof claim.json --verify --strict --json \
  --mission-contract contract.json --mission-sha256 EMPREINTE_ATTENDUE \
  --mission-pins trusted-witness-pins.json \
  --evidence-root ./evidence --source-root ./candidate
```

La commande historique `--verify --receipt-sha256 ...` reste inchangée.
Les trois arguments `--mission-*` sont nécessaires ensemble. Le fichier de pins
est un objet JSON `{ "criterion.json": "sha256...", "review.json": "sha256..." }`
fourni par le coordinateur de confiance, indépendamment du rapport de l'agent.
Copier des empreintes choisies par l'agent dans ce fichier annulerait cette
frontière de confiance. Aucun contrôle n'exécute de commande ou de modèle.

## Contrat avant l'exécution

Le [schéma](../schemas/verified-mission.schema.json) décrit les documents fermés.
Un contrat fixe une mission, une révision, une entrée, un vérificateur et tous les
critères obligatoires. Le coordinateur épingle ses octets avant l'exécution.

```json
{
  "schema": "botte.verified-mission/v1",
  "mission_id": "UO-network-pilot",
  "revision": "COMMIT_OU_EMPREINTE_CANDIDAT_EXACTE",
  "input": {"path": "trace.json", "sha256": "SHA256_ENTREE"},
  "verifier": {
    "id": "uo.multiplayer-pilot-check", "version": "1",
    "path": "scripts/check-multiplayer-pilot.mjs", "sha256": "SHA256_VERIFICATEUR"
  },
  "criteria": [
    {"id": "connexion", "description": "Les identités A et B sont distinctes"},
    {"id": "spawn", "description": "Les entités des deux joueurs sont distinctes"},
    {"id": "mouvement", "description": "Les déplacements sont autoritaires"},
    {"id": "pnj", "description": "Une réponse PNJ autoritaire est enregistrée"},
    {"id": "synchronisation", "description": "A et B reçoivent les mouvements de l'autre"},
    {"id": "reconnexion", "description": "A reprend son entité sans duplication"}
  ],
  "review": {
    "required": true, "implementer_id": "implementation-session",
    "brief_sha256": "SHA256_BRIEF_NEUTRE_ATTENDU"
  }
}
```

Les valeurs `SHA256_*` sont des repères, pas des empreintes valides. L'entrée et
le fichier du vérificateur doivent exister sous `--source-root`, correspondre
aux empreintes et figurer dans la portée de chaque reçu de tests utilisé. La
révision est une identité fournie par le coordinateur : ce contrôle ne consulte
pas Git et ne certifie pas tous les fichiers du dépôt. Inclure l'empreinte des
changements non committés dans l'identité lorsque nécessaire.

Une mission peut déclarer `"review": {"required": false}` si sa politique le
permet. Cela ne fournit aucune autorisation de fusion ou de clôture.

## Témoins de critères

Chaque critère référence un témoin distinct, épinglé par le coordinateur. Ce
témoin relie le critère au contrat et à un rapport de tests v1 inchangé :

```json
{
  "schema": "botte.mission-criterion/v1",
  "binding": {
    "contract_sha256": "SHA256_CONTRAT", "mission_id": "UO-network-pilot",
    "revision": "COMMIT_OU_EMPREINTE_CANDIDAT_EXACTE",
    "input_sha256": "SHA256_ENTREE",
    "verifier": {"id": "uo.multiplayer-pilot-check", "version": "1"},
    "criterion_id": "connexion"
  },
  "report_ref": "connexion-test-report.json",
  "receipt_sha256": "SHA256_RECU_TESTS_ATTENDU"
}
```

Le témoin est une déclaration du producteur de confiance selon laquelle les
tests cités vérifient ce critère. Le contrôle réutilise `verify_report` pour les
résultats, journaux et fichiers source ; il ne déduit pas la pertinence d'un test
de son nom. Un même run peut couvrir plusieurs critères si les témoins le
déclarent explicitement. Une liste absente, incomplète, dupliquée ou supplémentaire
de critères est refusée. Les chemins externes et liens symboliques sont refusés.

## Revue

La revue est un autre témoin épinglé. Son `binding` contient les mêmes champs que
ci-dessus, sans `criterion_id`. Elle ajoute :

```json
{
  "schema": "botte.mission-review/v1",
  "binding": {"contract_sha256": "SHA256_CONTRAT", "mission_id": "UO-network-pilot",
    "revision": "COMMIT_OU_EMPREINTE_CANDIDAT_EXACTE", "input_sha256": "SHA256_ENTREE",
    "verifier": {"id": "uo.multiplayer-pilot-check", "version": "1"}},
  "criteria_sha256": "SHA256_ENSEMBLE_TEMOINS",
  "reviewer_id": "review-session", "state": "completed", "decision": "accepted",
  "brief": {"path": "review-brief.txt", "sha256": "SHA256_BRIEF_NEUTRE_ATTENDU"},
  "output": {"path": "review-output.txt", "sha256": "SHA256_SORTIE_REVUE"}
}
```

`criterion_witness_digest({criterion_id: trusted_witness_sha256, ...})` calcule
`criteria_sha256` avec le module `skills.completion_proof.mission`. Une nouvelle
preuve de critère invalide donc la revue précédente, même si la révision Git
déclarée reste la même. Le coordinateur doit fournir un brief neutre (portée,
révision, comportement attendu et preuves brutes) avant le récit du développeur.
Le contrôle vérifie les octets attendus du brief ; il ne juge pas sa neutralité.

Les états `requested`, `running`, `failed`, `interrupted`, `quota_exhausted`,
`cancelled`, `timed_out` et `unknown` restent explicitement incomplets.
`quota_exceeded` est un alias accepté pour les producteurs qui l'utilisent déjà ;
le résultat conserve l'état reçu, sans le remplacer silencieusement. Aucun de ces
états ne vaut une revue terminée, même avec `decision: accepted`. La sortie et
le brief peuvent être `null` tant que la revue est incomplète. Pour `completed`,
ils doivent être non vides et leurs empreintes doivent correspondre. Une décision
autre que `accepted` bloque. L'identité déclarée du relecteur doit différer de
celle de l'implémenteur ; cette comparaison n'atteste pas leur indépendance réelle.

## Rapport et résultat

Le rapport de fin `botte.mission-completion/v1` contient exactement `schema`,
`status: complete`, `mission_id`, `contract_sha256`, `criteria` (liste de
`{id, witness_ref}`) et `review_ref` (chemin du témoin de revue, ou `null` si la
revue n'est pas requise).

En mode strict, seuls `verified: true`, aucun code d'erreur et le statut exact
`verified_on_mission_criteria` retournent 0. Les codes existants 3–7 restent
utilisés pour preuve manquante/invalide, test échoué, annonce et erreur d'accès.
Le code 8 indique une revue incomplète et 9 une revue non acceptée. Le mode sans
`--strict` reste un rapport de diagnostic et retourne 0 ; ne pas l'utiliser comme
barrière d'acceptation.

`authorizes_task_transition` reste `false` : Kanboard et l'opérateur conservent
leurs règles de transition. Les empreintes prouvent une correspondance, pas la
vérité d'un journal, la bonne exécution du jeu, ni une autorisation de publication.
Le scénario UO ci-dessus est un exemple d'intégration ; une trace fabriquée ou
une suite unitaire réussie ne valide pas le parcours multijoueur réel.

## Contrôles reproductibles

`python -m skills.completion_proof.test_verify` inclut les régressions de mission
dans la suite canonique existante. Les cas couvrent un vrai unittest puis une
entrée modifiée, une invocation CLI stricte, les preuves absentes/périmées, la
réutilisation d'une ancienne revue, la portée du brief et les états quota/échec.
Ces essais ne lancent ni Odin ni un modèle, et ne déploient pas le contrôle.
