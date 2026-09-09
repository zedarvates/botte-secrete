# Démarrer la mémoire commune sur le homelab

Ce guide prépare un service sur **un seul hôte Linux** et des clients MCP
sur les autres machines. Aucun hôte n'a été installé depuis cette session.
Le stockage SQLite reste sur l'hôte du service ; les clients utilisent l'API.

## 1. Initialiser deux identités

Sur l'hôte choisi, utiliser Python 3.10 ou plus récent et un checkout de la
branche `feat/shared-memory-scribe-v1` dans `~/botte-secrete`. Vérifier son commit
avec la [PR #111](https://github.com/zedarvates/botte-secrete/pull/111).
Les commandes suivantes partent de la racine de ce checkout :

```bash
/usr/bin/python3 --version
/usr/bin/python3 -m skills.memory_hub.cli init \
  --directory "$HOME/.local/share/botte-memory-pilot" \
  --project homelab-pilot --agent codex --agent hermes
```

L'initialisation exige un répertoire neuf et produit :

| Fichier | Usage |
|---|---|
| `agent-codex.secret` | Identité normale `codex` : lecture, écriture et oubli de ses données. |
| `agent-hermes.secret` | Identité normale `hermes`, avec les mêmes droits et son propre secret. |
| `operator.secret` | Entrée utilisateur de confiance et relecture ; reste hors des outils des agents. |
| `auth.json` | Association des identités, projets, droits et fichiers de secrets. |

Les secrets sont créés avec des permissions réservées au propriétaire sous
POSIX. Ils ne sont pas imprimés. Les noms doivent être uniques, y compris
sans tenir compte de la casse ; `operator` est réservé. Le mode historique
sans `--agent` conserve `worker.secret` et `operator.secret`.

## 2. Lancer le service

Un premier lancement au premier plan permet de vérifier les chemins :

```bash
/usr/bin/python3 -m skills.memory_hub.cli serve \
  --directory "$HOME/.local/share/botte-memory-pilot" --port 8766
```

Pour le service utilisateur persistant, arrêter ce lancement avec Ctrl+C,
puis vérifier les chemins dans le [modèle systemd](examples/botte-memory-pilot.service).
Il suppose `~/botte-secrete`, `/usr/bin/python3` et le répertoire de données
ci-dessus. Adapter le modèle avant de l'installer si ces chemins diffèrent.

```bash
mkdir -p "$HOME/.config/systemd/user"
cp docs/examples/botte-memory-pilot.service "$HOME/.config/systemd/user/"
systemd-analyze --user verify "$HOME/.config/systemd/user/botte-memory-pilot.service"
systemctl --user daemon-reload
systemctl --user enable --now botte-memory-pilot.service
systemctl --user status botte-memory-pilot.service --no-pager
```

Le modèle utilise `%h` pour le répertoire personnel et borne les redémarrages
automatiques. Ces paramètres suivent les
[directives officielles systemd](https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml).
La persistance du gestionnaire utilisateur après déconnexion ou au démarrage
de l'hôte dépend de sa configuration, notamment du mode *linger* : elle reste
à vérifier sur la machine. La validation syntaxique du modèle ne prouve pas
qu'un service fonctionne ou survit à un redémarrage de l'hôte.

Le serveur écoute seulement sur `127.0.0.1:8766`. Pour un autre ordinateur,
utiliser un tunnel SSH vers cet hôte ou une origine HTTPS déjà configurée.
Le client refuse HTTP sur le réseau distant et les redirections. Le
[guide API](shared-memory.md) précise le réglage du Host pour un proxy.

## 3. Exécuter l'acceptation avec deux identités

Sur l'hôte, depuis un second terminal :

```bash
/usr/bin/python3 -m skills.memory_hub.cli smoke \
  --url http://127.0.0.1:8766 --project homelab-pilot \
  --token-file "$HOME/.local/share/botte-memory-pilot/agent-codex.secret" \
  --peer-token-file "$HOME/.local/share/botte-memory-pilot/agent-hermes.secret"
```

Cette commande effectue dix contrôles : captures synthétiques partagée et
privée, lecture de l'autre identité par un vrai processus MCP, confidentialité,
quarantaine, refus de correction par le pair, correction du propriétaire avec
réessai, lecture de cette correction, disparition après oubli et refus du rejeu.

Elle utilise deux clés uniques `memory-smoke-...` et essaie de nettoyer ses
observations dans tous les cas, même lorsqu'une réponse d'écriture est perdue.
Les souvenirs préexistants restent hors de ce périmètre. Le nettoyage réussi
laisse les petites empreintes anti-rejeu prévues par l'API ; les données d'essai
et leur historique sont supprimés du service actif.

Le code de sortie vaut `0` si les contrôles et le nettoyage réussissent, `2`
si l'acceptation échoue, `1` pour une erreur de configuration. Le rapport JSON
ne contient ni secrets, ni URL du service, ni contenu des souvenirs. Si
`cleanup.complete` vaut `false`, ses `pending_keys` désignent les données
synthétiques à vérifier avec l'identité qui les a créées. Une interruption
forcée du processus peut aussi laisser des essais ; ils expirent pour la
recherche après une heure, mais cela n'efface pas leur historique.

**Ce test prouve une communication avec le service sous deux identités.** Les
deux processus peuvent être sur le même ordinateur :
`real_machine_pair_verified` reste donc `false`. Un essai réel Odin/Glyph ou
Odin/Thor demande ensuite une écriture depuis un client et sa lecture depuis
l'autre machine, avec leurs connexions effectivement ouvertes.

## 4. Brancher chaque client MCP

Sur chaque machine cliente, disposer du checkout et transférer uniquement son
fichier d'identité normale par le canal privé utilisé pour administrer l'hôte.
Restreindre les permissions du fichier ou son ACL Windows au compte concerné.
Les chemins du client peuvent différer de ceux du serveur.

Depuis le checkout du client, produire sa configuration avec ses vrais chemins :

```bash
python -m skills.memory_hub.cli client-config \
  --url http://127.0.0.1:8766 \
  --token-file /absolute/private/agent-codex.secret
```

Ici `127.0.0.1:8766` désigne le service local ou le tunnel ouvert sur le client.
Pour un proxy distant, fournir son origine HTTPS. La sortie JSON contient les
chemins de l'interpréteur, du checkout et du secret, jamais le secret lui-même.
Ajouter l'entrée `botte-shared-memory` à la configuration MCP du runtime choisi
en conservant ses autres serveurs. Cette commande ne modifie pas cette
configuration et n'établit pas de connexion à elle seule.

Sur le second client, générer la configuration avec `agent-hermes.secret`.
Utiliser ensuite `memory_checkpoint` et `memory_recall` avec le projet
`homelab-pilot` et `area=observations` pour les rapports d'agents. La relecture
de faits utilisateur suit toujours le circuit séparé de l'opérateur.

## Arrêt et reprise

```bash
systemctl --user disable --now botte-memory-pilot.service
```

L'arrêt conserve les données. Après une modification de `auth.json`, redémarrer
le service pour charger les droits actualisés. Conserver le checkout précédent
pour un retour de code ; ne pas restaurer une ancienne base sans réconcilier
les oublis récents. Le [parcours de sauvegarde et restauration](shared-memory-recovery.md)
prépare une nouvelle base avec réconciliation des oublis. Les sauvegardes
planifiées et la bascule du service restent des opérations distinctes.
