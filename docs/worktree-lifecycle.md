# Relier les worktrees aux résultats acceptés

`scripts/worktree_lifecycle.py` rapproche l'inventaire Git actuel, les missions,
les PR et leurs résultats. Il produit un **plan de revue en lecture seule** :
il ne supprime aucun fichier, worktree, branche ou référence, ne lance aucun
agent, et n'exécute ni `worktree prune`, ni `worktree remove`, ni `reset`.

Depuis la racine du dépôt, avec Python 3.10+ et Git disponibles :

```bash
python scripts/worktree_lifecycle.py --repo /chemin/depot --target main --records /chemin/records.json
```

`--target` désigne une référence locale existante. Le script ne fait aucun fetch
et ne présume pas que `main` ou `origin/main` correspond à l'état actuel distant.
Choisir une référence dont la fraîcheur a été contrôlée séparément.

Le manifeste versionné contient des observations explicitement fournies :

```json
{
  "schema": "botte.worktree-lifecycle/v1",
  "records": [
    {
      "path": "/chemin/worktree-termine",
      "task_id": "TASK-123",
      "task_state": "accepted",
      "activity": "idle",
      "activity_observed_at": "2026-11-02T15:00:00Z",
      "pull_request": {
        "url": "https://github.com/owner/repo/pull/123",
        "state": "merged",
        "head_sha": "REMPLACER_PAR_LE_HEAD_EXACT_40_HEX",
        "merge_sha": "REMPLACER_PAR_LE_COMMIT_INTEGRE_40_HEX"
      },
      "proof": {
        "head_sha": "REMPLACER_PAR_LE_HEAD_EXACT_40_HEX",
        "evidence_root": "/chemin/preuves",
        "report": "report.json",
        "trusted_receipt_sha256": "REMPLACER_PAR_EMPREINTE_FOURNIE_PAR_EXECUTEUR"
      }
    }
  ]
}
```

Ces valeurs sont illustratives et sont refusées telles quelles. La racine des
preuves et les chemins des worktrees sont explicites. Le rapport de résultat
réutilise le [vérificateur de preuves existant](../skills/completion_proof/verify.py),
avec `run_id` égal à `task_id`. La mission, le HEAD et l'empreinte du reçu doivent
être rapprochés par l'hôte depuis ses journaux fiables. Une empreinte récupérée
uniquement depuis le rapport à contrôler ne fournit pas ce point de confiance.

Un worktree devient `candidate_for_owner_review` seulement si :

- il appartient à l'inventaire Git, reste propre, sans fichier non suivi ou
  ignoré (y compris les configurations locales), et
  n'est ni le worktree principal, ni détaché, verrouillé ou à réparer ;
- la mission a été acceptée et l'activité est déclarée inactive avec une
  observation datée de moins de cinq minutes, sans date future ;
- la PR est déclarée fusionnée, son HEAD est exactement celui du worktree, et
  le HEAD comme le commit de fusion sont ancêtres de la cible locale ;
- le reçu épinglé passe le vérificateur existant pour les fichiers du worktree,
  et le résultat appartient à la mission indiquée ;
- HEAD, cible et état propre restent identiques au contrôle final.

Tout élément actif, inconnu, sale, sans provenance ou non intégré est conservé
avec un motif explicite. Une fusion squash/rebase dont le HEAD initial n'est
plus ancêtre est conservée également : ce script n'invente pas d'équivalence de
contenu. Les liens symboliques et jonctions de chemins d'entrée sont refusés.

Les statuts de PR et d'exécution restent **déclarés par l'appelant** : le script
n'interroge ni GitHub, ni Odin, ni les processus. Le vérificateur établit
l'intégrité du reçu et des fichiers listés, pas la complétude métier de tous les
tests ni la véracité d'un émetteur non fiable. `candidate_for_owner_review` ne
donne donc aucune autorisation de suppression. Le rapport est un instantané ;
une opération ultérieure exige une nouvelle inspection des changements et des
travaux encore actifs dans le cadre de ses autorisations propres.

Les manifestes sont limités à 1 Mo et 256 entrées, chaque sortie Git à 2 Mo et
15 secondes, et le rapport JSON à 2 Mo. L'inventaire conserve le nombre total et
le nombre omis au-delà de 256 worktrees ; `complete=false` interdit de présenter
le plan comme exhaustif. Une limite dépassée ou un échec Git ne devient jamais
une preuve d'absence de travail.

Validation reproductible sur de vrais dépôts Git temporaires :

```bash
python scripts/test_worktree_lifecycle.py -q
```

Les cas couvrent une fusion propre, des modifications suivies/non suivies/ignorées, un
nouveau commit local, une mission active/inconnue, des preuves manquantes ou
altérées, un résultat d'une autre mission, des liens de chemins, les limites de
couverture et l'interface CLI. Ils ne qualifient pas un nettoyage réel sur Odin.
