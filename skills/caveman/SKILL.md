---
name: caveman
description: "Produire un prompt de réponse concise ou analyser la taille d'un fichier en lecture seule. Ne compresse pas le fichier et ne mesure pas les économies d'un modèle."
---

# Caveman — concision explicite

Utiliser `prompt` pour obtenir une instruction de style à transmettre explicitement
au modèle. Conserver la langue demandée, les négations, conditions, incertitudes,
commandes, identifiants, preuves et conséquences. Privilégier la clarté.

| Niveau | Style demandé |
|---|---|
| `light` | Phrases courtes, sans remplissage |
| `full` | Phrases ou fragments sans ambiguïté |
| `ultra` | Un point court par ligne, avec les explications nécessaires |
| `classical` | Chinois classique uniquement sur demande explicite de l'utilisateur |

```bash
python -m skills.caveman.cli prompt --level light
python -m skills.caveman.cli compress mon_fichier.md --format json
python -m skills.caveman.cli stats
```

`compress` conserve son nom historique : il lit le fichier complet sans le modifier
et rend une analyse de taille. `--dry-run` est un alias de ce comportement.
Les octets UTF-8 sont mesurés ; les tokens sont estimés par caractères/4.
Le texte rendu reste intact, son gain est donc nul. `style_savings_pct: null`
signifie que le gain d'une future réponse du modèle reste non mesuré.

Les prompts sont dans `prompts.py`. Ces commandes n'injectent pas automatiquement
de prompt et ne modifient ni le routage ni le budget de raisonnement.
Comparer des sorties réelles appariées et leur qualité avant de publier un gain.
