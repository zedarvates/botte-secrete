# Clarification ciblée

Préparer des questions utiles sans imposer d'entretien avant chaque tâche.
Lire d'abord le contexte du projet et les décisions existantes. Une demande
claire et déjà autorisée peut être exécutée directement ; les générateurs
fournissent seulement des candidats à adapter.

## Règles

- Réutiliser les réponses et autorisations acquises ; ne pas les redemander.
- Poser seulement les questions dont la réponse change matériellement le travail.
- Choisir au besoin un défaut pour un détail réversible dans le périmètre
  autorisé et présenter ce défaut comme une hypothèse.
- Garder une réponse manquante à un blocage ou à une autorisation en attente.
  Silence, timeout et `auto` ne la résolvent jamais.
- Continuer les étapes indépendantes pendant l'attente.

## API

```python
from skills.clarification import dartagnan_clarify

request = dartagnan_clarify(3)
# Réponse déjà établie dans la demande : ne pas redemander son autorisation.
known = {1: "Corriger ces trois défauts sur la branche isolée, autorisé."}
prompt = request.to_prompt(known)
assumptions = request.fill_defaults(known)
pending_blockers = request.blocking_questions(known)
```

`pending_questions(answers)` masque les réponses connues, sans modifier la
requête. Les réponses vides ou égales à `auto` restent inconnues.
`to_prompt(answers)` renvoie une chaîne vide lorsque tout est résolu.
`fill_defaults(answers)` omet les questions sans défaut, les BLOCKER et celles
marquées `requires_explicit_answer=True`, quelle que soit leur priorité.
L'appelant doit examiner les blocages restants avant une étape dépendante.

La valeur `answers` vient du contexte établi par l'appelant. Ces fonctions ne
vérifient pas son authenticité et ne contrôlent pas l'exécution d'actions ;
les permissions de l'hôte restent applicables. Une hypothèse n'est jamais une
autorisation, même si le texte du défaut contient « oui ».

## Générateurs disponibles

| Agent | Fonction | Candidats |
| --- | --- | --- |
| Porthos | `portos_clarify()` | Périmètre, exclusions, orientation d'audit |
| d'Artagnan | `dartagnan_clarify()` | Périmètre des corrections, commits, tests |
| Aramis | `aramis_clarify()` | Objectif, appels dynamiques, budget |
| Rochefort | `rochefort_clarify()` | Portée du contre-audit, frameworks |

Validation : `python -m skills.clarification.test_clarification`.
