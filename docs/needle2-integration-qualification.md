# Needle 2 : archives historiques et logiciel intégré

Le pilote est consultatif. Son étude historique reste arrêtée avec
`stop_insufficient_safe_coverage` et `selected_threshold: null`. L'intégration
du logiciel ne qualifie ni le modèle, ni un seuil, ni un routage automatique.

## Deux vérifications distinctes

La CI reproduit les archives depuis le commit exact
`02be6033c7a73788643ee5e7cf6ad6e071394e02`, dans un job séparé. Elle vérifie
ce SHA puis exécute les tests historiques de preuves et de diagnostic. Aucun
modèle, poids ou service mémoire n'est lancé. Ces contrôles vérifient l'intégrité
des archives et le recalcul de leurs scores ; ils n'attestent pas indépendamment
les anciennes inférences.

La matrice courante vérifie le logiciel intégré avec des moteurs factices et
un protocole de test temporaire distinct. Ses deux lots factices de 20 cas
ne sont ni les corpus historiques ni une nouvelle mesure de qualité modèle.
Le protocole temporaire ne remplace aucun fichier conservé dans le dépôt.

Les sources intégrées ont changé, notamment le CLI, le contrat partagé de
mémoire et la façade consultative. Certains anciens attachements de preuves
étaient également des sources/tests. Les commandes historiques `needle2_study`
et `needle2_diagnostics` doivent donc refuser ces anciennes preuves sur le
checkout courant, avant initialisation d'un moteur ou écriture de résultat.
Ce refus est vérifié. Il ne faut pas actualiser les anciennes empreintes pour
obtenir artificiellement une reproduction sur de nouvelles sources.

Pour reproduire exactement l'étude, utiliser un checkout isolé au SHA ci-dessus
et ses instructions historiques. La validation réservée de l'étude n'a pas été
exécutée et reste fermée. Toute nouvelle étude demande un protocole distinct,
figé avant inférence, et ses propres données d'évaluation.

## Opérations actuelles

```bash
botte needle2 tools
python -m skills.tool_router.argument_spans --input demande.json --output proposition.json
python -m skills.tool_router.test_runner
python -m skills.execution_harness.test_execution_harness
```

`tools` consulte les cinq schémas autorisés, sans démarrer de worker. La copie
de passages exige une requête et une proposition explicites, liées par SHA-256.
Elle conserve les caractères et positions Unicode ; elle ne choisit pas le bon
outil ou le bon passage et ne détecte pas la négation. Elle produit un nouveau
fichier exclusif ; aucun appel mémoire n'est effectué. L'entrée doit être un
fichier régulier de 8 192 octets au maximum ; une FIFO ou un lien détecté est
refusé. Ce contrôle n'est pas un bac à sable du système de fichiers.

`propose()` force désormais `route.executable: false` quel que soit l'adaptateur
fourni, y compris le routeur lexical. Les propositions conservent
`executed: false`, `activation_allowed: false` et zéro appel/écriture mémoire.
Un champ `memory_call` est une proposition à examiner, jamais un appel effectué.

L'ancien résultat JSON d'exemple conserve l'empreinte de son ancien binder.
Un nouveau résultat porte l'empreinte du binder réellement exécuté. Le test
compare le comportement fonctionnel et distingue ces identités de source,
sans réécrire l'archive pour la faire correspondre au nouveau code.

## Contrats du harnais

Le harnais hérité de cette PR reste une couche de contrats en mémoire.
L'intégration corrige trois frontières : les deltas enregistrés sont copiés
profondément et revalidés avant transmission ; un checkpoint est reconstruit
depuis l'état courant ; l'amorce Atlas n'accepte que les octets du comparatif
historique lié à son SHA-256 et à son protocole. Ses mesures doivent être finies
et respecter leurs dénominateurs.

Une déclaration d'évidence vérifiée, un identifiant de récupération ou un avis
de licence ne constitue pas une attestation externe. Le harnais ne découvre pas
les droits des poids, ne prouve pas les effets distants et ne donne pas de
permission d'exécution ou de promotion.
