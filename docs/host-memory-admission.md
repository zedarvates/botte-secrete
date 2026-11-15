# Admission mémoire des superviseurs locaux

La file Codex en mode réel et le récepteur des commandes nommées utilisent
`skills.host_resources.HostMemoryGuard`. Cette admission est locale à chaque
poste. Elle ne remplace pas un plafond mémoire imposé par le système.

## Conditions de départ

- Mesure fraîche (au plus deux secondes), avec horodatage UTC et monotone.
- Windows : RAM physique disponible **et** engagement disponible, lus par
  `GlobalMemoryStatusEx`. Linux : `MemAvailable` et les limites cgroup v2 visibles,
  y compris les parents. Une limite mémoire v1, hybride ou non observable est
  refusée plutôt que traitée comme une capacité illimitée.
- Marge système : le maximum de 2 Gio et 10 % de la mémoire totale effective.
- Somme de tous les budgets réservés, plus le nouveau budget et la marge,
  inférieure ou égale à la RAM disponible et à l'engagement disponible Windows.
- Écriture atomique de la réservation sous verrou interprocessus, avant départ.
  Une seconde mesure précède le lancement. Une panne de mesure, de verrou ou de
  registre refuse le départ. Un registre corrompu ou disparu n'est pas réinitialisé.

Le budget par défaut est de 4 Gio par tour ou commande nommée. La file réserve
aussi 512 Mio avant de lancer son propre `app-server`. Ce budget est libéré
après l'arrêt constaté de ce processus. Le formulaire ou l'API peut déclarer
`estimated_ram_gib` par tour ; les commandes nommées acceptent la même option
dans leur configuration opérateur. Les valeurs non finies, booléennes, négatives
ou hors de 0,25–1024 Gio sont refusées.

Le calcul est volontairement conservateur : un budget réservé est compté en
entier, même si une partie de sa consommation figure déjà dans la mesure OS.
Cela peut retarder un départ ; le calcul ne promet pas un débit maximal.

## Un registre commun par poste

Par défaut, le registre est `botte-secrete/host-memory.json` sous
`LOCALAPPDATA`, `XDG_STATE_HOME` ou `~/.local/state`. Toutes les instances
participantes du même poste doivent utiliser **le même chemin absolu**, par
`BOTTE_RESOURCE_STATE` ou `--resource-state` pour la file. Les comptes et
services différents doivent être configurés explicitement pour partager ce
chemin et ses permissions existantes. Ne pas placer le registre sur un partage
réseau ni partager un registre entre deux postes.

Le plafond de cinq tours et les exclusions de dossiers restent propres à une
file ; seuls les budgets mémoire sont partagés. Les sessions natives, les
services privés et les autres superviseurs doivent intégrer ce garde-fou pour
réserver leur croissance prévisionnelle. Leur RAM déjà consommée figure dans
la mesure OS. Le choix LRU d'un backend n'est pas une admission mémoire.

## Arrêt, reprise et réconciliation

Une fin de tour ou un code de sortie 0 ne prouve pas que ses descendants ou les
services démarrés sont arrêtés. Les budgets de tours et de commandes restent
donc réservés après leur retour. Aucun TTL, changement de PID ou redémarrage
ne libère ces budgets automatiquement. La file importe aussi les budgets des
anciens travaux occupés ou inconnus avant toute nouvelle admission, même si
la mémoire actuelle est insuffisante. Les terminaux en attente de réconciliation
conservent également leur budget au redémarrage.

Après vérification de l'arrêt du travail, de ses sous-processus et services,
utiliser **Confirmer l'arrêt vérifié** sur sa carte. Pour une commande nommée
ou une réservation laissée par un crash, le propriétaire local peut consulter
les clés puis libérer uniquement la clé vérifiée :

```powershell
python -m skills.host_resources status
python -m skills.host_resources release 'cle-exacte-retournee' --stopped-confirmed
```

`--state CHEMIN_ABSOLU` choisit le registre explicite. `status` conserve la liste
des réservations valides si la mesure est indisponible ; son code de sortie
reste non nul si l'admission est refusée. Ne pas supprimer un registre ou son
verrou pour débloquer une file. Si le registre est endommagé, conserver les
fichiers et réconcilier les exécutions avant de restaurer un état cohérent.

Les diagnostics du récepteur restent accessibles lorsque la mémoire est basse.
Le garde-fou suspend les nouveaux départs ; il n'interrompt pas les travaux
déjà actifs et ne limite pas leur croissance. Une estimation insuffisante doit
être corrigée. Le code ne configure pas de service et ne déploie rien à distance.

## Vérification avant activation sur un poste

1. Relever la version installée, les superviseurs actifs et les budgets occupés.
2. Choisir le registre local commun et vérifier la mesure avec `status`.
3. Exécuter les suites `skills.test_host_resources`,
   `scripts/test_odin_codex_queue.py` et `skills.cluster.test_cluster`.
4. Vérifier le refus d'une estimation supérieure à la capacité disponible,
   la conservation après coupure et la libération après arrêt réel vérifié.
5. Qualifier la version Windows/Linux sur la cible avant usage quotidien.

Les tests déterministes et le faux app-server vérifient le code. Ils ne prouvent
ni une installation effective sur les postes ni le comportement matériel Windows.
