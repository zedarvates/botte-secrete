# File locale Codex sur Odin

Ce pilote lance au maximum **cinq tours Codex** à la fois. Les suivants portent
un badge « File nº 1 », « File nº 2 », etc., recalculé à chaque départ ou retrait.
Le tableau de bord se rafraîchit toutes les secondes, sans appel à un modèle.
Il gère uniquement les lancements soumis par son formulaire. Les discussions
ouvertes directement dans l'application Codex échappent à cette limite.

## Démarrage réversible

Prérequis : Python 3.10+, dépôt Botte Secrète et, pour le mode réel, Codex CLI
installé et déjà connecté à ChatGPT. Aucun paquet Python supplémentaire.
Le programme reste au premier plan ; aucun service Windows n'est installé.

Depuis la racine du dépôt, sous Windows :

```powershell
python scripts/odin_codex_queue.py
```

Ouvrir dans le navigateur local l'URL imprimée. Elle contient un jeton privé :
ne pas la publier. Le mode par défaut est **Simulation** ; « Essayer avec
8 discussions » montre cinq exécutions et trois badges, sans lancer de modèle
ni modifier les dossiers de travail.

Pour le mode réel, remplacer les chemins ci-dessous par les chemins vérifiés
sur Odin. Répéter `--root` pour chaque dossier de projets autorisé :

```powershell
python scripts/odin_codex_queue.py --live --root 'F:\chemin-verifie\projets' --codex-executable 'C:\chemin-verifie\codex.exe'
```

Utiliser le vrai binaire `codex.exe`, pas un wrapper `.cmd` ou `.bat`. Le programme
refuse un compte API ou un fournisseur sans authentification OpenAI ; il ne
connecte pas de compte et ne change pas de modèle. La connexion ChatGPT est
vérifiée avant chaque départ. Les limites de l'abonnement continuent à s'appliquer.
`--max-running` accepte 1 à 5 ; sa valeur par défaut est 5.

## Comportement

- Les démarrages, validations et interruptions en attente occupent une place.
  Un accusé d'interruption ne suffit pas : le pilote attend la fin du tour.
- Les dossiers identiques ou imbriqués et les reprises de la même discussion
  sont exclusifs. Une mission indépendante peut passer devant une mission bloquée.
  Pour travailler en parallèle sur un dépôt, utiliser des worktrees distincts.
- Les chemins sont validés à la soumission et avant le départ. Seuls les
  dossiers existants sous les racines autorisées peuvent être utilisés.
- L'audit utilise le sandbox `readOnly`, les autres missions `workspaceWrite`.
  Les demandes de validation de commande ou fichier sont affichées et requièrent
  une décision pour l'action concernée. Les autres demandes restent bloquées ;
  interrompre le tour pour reprendre dans le client natif.
- « Suspendre les départs » conserve les tours déjà lancés. « Interrompre »
  demande l'arrêt d'un tour ; « Retirer de la file » annule un travail non lancé.
- Les soumissions répétées avec la même clé sont idempotentes. Après une coupure,
  les tours potentiellement actifs sont marqués « État à vérifier » et aucun
  nouveau tour ne démarre. Confirmer leur arrêt réel avant de libérer leurs places.
  Aucune mission n'est rejouée automatiquement.
- « Tour terminé · à revoir » signifie que Codex a terminé son tour, pas que
  les critères métier sont prouvés. Kanboard conserve le suivi métier et sa
  politique d'autonomie ; ce pilote ne modifie pas cette politique.

## État local et arrêt

La file, ses demandes et ses résultats sont enregistrés en clair dans un fichier
JSON local sous `%LOCALAPPDATA%\botte-secrete\odin-queue` (XDG sous Linux).
Simulation et mode réel utilisent des fichiers séparés. Ne pas y soumettre de
secrets. `--state` permet un emplacement privé explicite. Un verrou système
empêche deux superviseurs de partager le même fichier. Le fichier est écrit
atomiquement ; aucun service de base de données n'est nécessaire.

Le serveur écoute uniquement `127.0.0.1`. Les API vérifient le jeton et l'origine.
Ne pas exposer ce port sur le réseau. Fermer avec Ctrl+C : le pilote ferme
seulement son propre processus `codex app-server`. Vérifier les tours encore
occupés au redémarrage. Supprimer les fichiers locaux uniquement après avoir
vérifié l'arrêt des travaux, si l'on veut effacer l'historique.

## Validation et limite de livraison

```powershell
python scripts/test_odin_codex_queue.py
python scripts/pre-commit-check.py --fast
```

18 tests couvrent la concurrence réelle du superviseur, les positions et leur
renumérotation, les conflits de chemins/discussions, la reprise durable, les
validations, les interruptions, les courses du protocole stdio et les protections
HTTP. Le raccordement app-server est testé avec un processus factice, sans modèle.
Le contrôle du compte API vérifie le refus avant lancement.

La validation a été réalisée sous Linux. L'essai graphique complet et un vrai
tour Codex sous Windows restent à réaliser sur Odin avant activation quotidienne.
Le pont Odin hors ligne ne constitue pas une preuve d'installation.

Protocole officiel : <https://learn.chatgpt.com/docs/app-server>.
