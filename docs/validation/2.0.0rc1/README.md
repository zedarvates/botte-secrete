# 2.0.0rc1 — rapports et reproduction

Ces résultats datés du **13 septembre 2026** portent sur la préversion
[v2.0.0rc1](https://github.com/zedarvates/botte-secrete/releases/tag/v2.0.0rc1),
commit `d98505fd6586ff3d0d32a2cb4ebd5f0408d4142a`.
Les fichiers publics excluent les chemins locaux et journaux bruts.

## Installation propre

| Vérification | Windows 11 / Python 3.14.0 | Ubuntu WSL2 / Python 3.12.3 |
|---|---|---|
| Installation depuis GitHub | Réussie | Bloquée par le DNS WSL |
| Installation hors ligne du wheel issu du tag | Non nécessaire | Réussie |
| Version, provenance, dépendances (`pip check`) | Réussies | Réussies |
| CLI `--help` et `belt` | Réussies | Réussies |
| MCP stdio : initialize, tools/list, find_tool, ping | Réussi | Réussi |
| Factory Assurance : core / intégrations / rôles | 13 + 12 + 10 réussis | 13 + 12 + 10 réussis |

Rapports : [Windows](windows.json), [Linux](linux.json).
Venv neufs, paquet non éditable, tests hors dépôt et imports depuis site-packages.
Les processus testés ont un répertoire utilisateur isolé et l'auto-étiquetage
NN désactivé. Aucun appel de modèle. Les 5 outils MCP visibles correspondent
au mode lazy ; tous les outils ne sont pas exercés.

Le wheel Linux a été construit depuis le tag sur Windows, puis installé avec
des dépendances Linux téléchargées depuis Windows. Son SHA-256 est
`49ffa989764b26a2a8ee96d19085acb256b49363e43aedd3f51a290283b01f42`.
Ce test WSL ne valide pas le téléchargement direct sous Linux. Le workflow
ci-dessous exerce ce parcours séparément sur un runner Ubuntu.

## Pilote sur code public externe

Cible : [python-slugify au commit figé](https://github.com/un33k/python-slugify/tree/fee5aa338d3bd7a9e36c269e33b496a7848edc44),
licence MIT. Périmètre : paquet `slugify` et `test.py` ; pas toute la suite du dépôt.

| Cas | Tests | Échecs | Décision Botte |
|---|---:|---:|---|
| Original | 82 | 0 | hold : revue indépendante et holdout manquants |
| Conversion en minuscules retirée | 82 | 24 | hold : tests échoués et preuves manquantes |
| Limite de longueur retirée | 82 | 7 | hold : tests échoués et preuves manquantes |
| Filtrage des stopwords retiré | 82 | 12 | hold : tests échoués et preuves manquantes |

[Rapport](pilot.json) · [Protocole enregistré avant exécution](pilot-protocol.json).
Les trois mutations sont effectuées sur des copies ; les assertions upstream
restent inchangées, avec vérification de leur empreinte. Les tests du projet
détectent les défauts ; Botte évalue les preuves fournies. Aucun nouveau bug
upstream, accord du mainteneur ou validation humaine indépendante n'est revendiqué.
Le même opérateur a préparé et exécuté cette expérience. Elle ne mesure pas un
taux général de faux positifs ou de défauts manqués. Tous les cas restent hold.

## Relancer

Prérequis : Git, Python 3.12 recommandé, accès HTTPS à GitHub et PyPI. Le script
installe des dépendances dans un nouveau venv temporaire et conserve les
diagnostics localement. Aucune configuration de projet existant n'est modifiée.

Depuis un clone de Botte Secrète contenant ces scripts :

```bash
python scripts/release_validation/run.py --output rc1-public-reports
```

Le dossier de sortie doit être nouveau. La commande retourne un code non nul
en cas d'échec ; `summary.json` décrit l'étape concernée. Les journaux détaillés
restent dans le dossier temporaire affiché, hors des rapports publics.
Les étapes utilisent les commits figés et les
[versions de dépendances enregistrées](../../../scripts/release_validation/requirements.txt).
Le téléchargement et l'outillage de construction restent dépendants de leur
disponibilité ; ce protocole ne promet pas des wheels identiques bit à bit.
Les durées et identités des commits locaux peuvent varier ; comparer les
tests, les motifs de blocage et les Git trees des copies, pas leurs dates.

Sur GitHub : **Actions → RC1 report reproduction → Run workflow**.
Le [workflow](../../../.github/workflows/rc1-reproduction.yml) exécute Windows et
Ubuntu, puis fournit des artefacts JSON publics pendant 30 jours, y compris
un résumé en cas d'échec. Les rapports datés de cette page restent versionnés.

La suite complète historique de 960 tests n'est pas relancée par ce protocole.
Il cible l'installation, les points d'entrée et le pilote décrit ci-dessus.
La revue humaine indépendante et le holdout privé restent des jalons ouverts.
