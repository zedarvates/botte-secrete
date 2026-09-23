# Sauvegarde et restauration de la mémoire partagée

Ces commandes d'opérateur complètent le [pilote homelab](shared-memory-homelab.md).
Elles utilisent uniquement Python 3.10+ et SQLite. Elles ne sont pas exposées
aux agents dans l'API ou le MCP et n'activent aucun service.

## Sauvegarder un projet

Depuis le checkout contenant cette version :

```bash
python -m skills.memory_hub.cli backup --directory /absolute/private/memory-service --project homelab-pilot --output /absolute/private/backup-001
```

Le dossier parent doit exister et être privé ; `backup-001` doit être nouveau.
Le service peut fonctionner pendant la sauvegarde. L'[API de sauvegarde SQLite](https://sqlite.org/backup.html)
produit une image cohérente, y compris les écritures validées qui se trouvent
encore dans le journal WAL. Copier seulement le fichier `.sqlite` d'un service
actif ne constitue pas ce parcours.

Le résultat contient `snapshot.sqlite` et `manifest.json`. Le manifeste final
indique le projet, l'heure de fin et l'empreinte SHA-256 du fichier. Un dossier
sans manifeste final est incomplet. Le budget de copie est de 30 secondes ; une
activité continue ou une base trop grande peut nécessiter un arrêt de maintenance.

La sauvegarde contient les souvenirs du projet, leur provenance, l'historique,
les vecteurs, les reçus de réessai et les empreintes des clés oubliées. Elle
n'inclut ni `auth.json`, ni les jetons, ni les autres projets. Les fichiers sont
créés en mode 0600 dans un dossier 0700 sur POSIX ; les ACL Windows restent à
configurer et n'ont pas été testées ici.

Le contenu est en clair. Garder ces fichiers dans le stockage privé approprié,
avec sa protection habituelle. Le code ne configure ni chiffrement, ni réplication,
ni calendrier. Le checksum détecte une altération par rapport au manifeste ;
il n'authentifie pas l'auteur d'une copie dont le manifeste serait aussi remplacé.

## Préparer une restauration sans réintroduire les oublis connus

1. Arrêter les écritures du service actuel et les laisser arrêtées jusqu'à la
   décision de remise en service. Utiliser son gestionnaire habituel ; avec le
   modèle fourni, `systemctl --user stop botte-memory-pilot.service`.
2. Conserver le répertoire actuel : son registre d'oublis fait autorité. Ne pas
   le remplacer par celui de la vieille sauvegarde.
3. Créer un nouveau service privé avec les mêmes identifiants d'acteurs et les
   mêmes droits. L'exemple ci-dessous reprend les deux workers du guide initial ;
   adapter ces noms aux identités réellement utilisées. Les nouveaux jetons
   devront être distribués à leurs seuls clients par le canal privé existant.
4. Restaurer dans son sous-dossier `data` encore absent.

```bash
python -m skills.memory_hub.cli init --directory /absolute/private/memory-restored --project homelab-pilot --agent codex --agent hermes
python -m skills.memory_hub.cli restore --backup /absolute/private/backup-001 --current-directory /absolute/private/memory-service --output-data /absolute/private/memory-restored/data
```

`restore` vérifie le checksum, l'intégrité SQLite, le schéma et le projet. Il
refuse les schémas supplémentaires, les journaux annexes de la sauvegarde,
l'absence du registre actuel ou un registre ayant perdu des oublis déjà présents
dans la sauvegarde. Il ne migre pas une base d'une autre version.

Pour chaque empreinte oubliée dans le registre actuel, la nouvelle base retire
le souvenir, ses révisions, son vecteur et ses reçus. Elle conserve également les
interdictions de rejeu pour les clés créées puis oubliées après la sauvegarde.
Un [VACUUM SQLite](https://sqlite.org/lang_vacuum.html) compacte la nouvelle base
après suppression. La sauvegarde source et la base actuelle restent inchangées.

Exiger un code de sortie 0, `complete=true` et le rapport final `data/restore.json`.
Le rapport contient les empreintes et les nombres de clés réconciliées, sans
texte de souvenir, nom de clé ou jeton. Une interruption contrôlée renvoie 130
et retire le nouveau dossier incomplet. Une coupure brutale peut laisser un
dossier partiel sans rapport final ; ne pas le servir ni le confondre avec une
restauration terminée. Un dossier préexistant est toujours refusé.

## Vérifier avant de reprendre les clients

Le registre est lu sur une vue cohérente, mais le programme ne prouve pas qu'il
est le plus récent ni que les anciens writers sont arrêtés. C'est pourquoi
`ledger_freshness_attested=false` et `service_activated=false` restent explicites.
Si l'ancienne base a reçu une nouvelle écriture depuis cette lecture, préparer
une nouvelle restauration après arrêt des writers. Si le registre complet des
oublis est perdu ou douteux, ce parcours ne peut pas autoriser une reprise fiable.

La restauration retrouve l'état de la sauvegarde, amendé par les oublis connus.
Elle ne récupère pas les nouvelles captures, corrections ou relectures intervenues
ensuite : `post_backup_updates_recovered=false`. Vérifier la fraîcheur des faits
avant de les réutiliser. Les copies exportées, les archives des agents et les
anciennes sauvegardes restent en dehors de la suppression.

Une fois la nouvelle base et les droits inspectés, utiliser le [parcours de
lancement et de sonde](shared-memory-homelab.md) avec le nouveau répertoire et ses
deux jetons. Garder l'ancien service arrêté pour éviter deux bases divergentes.
La sonde teste des fixtures et leur nettoyage ; elle ne valide pas la justesse
du corpus restauré ni la connexion physique Eurekai → Odin.

## Preuve reproductible

```bash
python -m pytest --rootdir=. -q skills/memory_hub/test_recovery.py
```

Les tests exercent un vrai fichier SQLite avec WAL, une restauration après oublis,
les droits privés, la quarantaine, l'historique, le rejeu, les corruptions,
les destinations existantes et les interruptions, ainsi que les commandes CLI.
Voir le [relevé de validation](validation/shared-memory-recovery-v1.json).
Cette preuve locale ne constitue pas une recette de sinistre sur le homelab.
