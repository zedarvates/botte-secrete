# 🔍 Clarification Proactive — Module de questions intelligentes

> *"Pose-moi jusqu'à 5 questions numérotées pour t'éclaircir sur les points qui te paraissent pas assez définis."*

## Concept

Chaque agent (Mousquetaire ou Cardinal) **doit** poser jusqu'à 5 questions
avant de commencer son travail. Si l'utilisateur ne répond pas (silence,
timeout, ou "auto"), l'agent comble les vides avec des hypothèses raisonnables
ET les signale explicitement dans son rapport.

## Pourquoi ?

- **Évite le travail inutile** — L'agent ne part pas dans la mauvaise direction
- **Détecte les ambiguïtés tôt** — Avant d'avoir passé 5000 tokens
- **Respecte l'autonomie** — L'utilisateur peut répondre ou déléguer ("auto")
- **Traçabilité** — Chaque hypothèse est documentée dans le rapport

## Règles

1. **Maximum 5 questions** — Numérotées, concises, actionnables
2. **Priorité décroissante** — Les questions bloquantes d'abord
3. **Défaut explicite** — Chaque question a une réponse par défaut
4. **Silence = "auto"** — Si pas de réponse après 1 échange, utiliser les défauts
5. **Hypothèses documentées** — `⚠️ Hypothèse: [valeur]` dans le rapport

## Architecture

```
skills/clarification/
├── __init__.py          # Module principal
│   ├── Question         # Une question (numéro, priorité, défaut)
│   ├── ClarificationRequest  # Requête complète (max 5 questions)
│   └── Générateurs par agent (ex: portos_clarify, aramis_clarify)
```

## Intégration

Chaque pré-prompt d'agent inclut maintenant :

```markdown
## 🔍 Clarification Proactive (OBLIGATOIRE avant de commencer)

**Pose jusqu'à 5 questions numérotées** pour éclaircir les points ambigus.

Questions types pour [Agent] :
1. Question prioritaire ?
2. Question secondaire ?

**Règle du silence :** Si l'utilisateur ne répond pas ou dit "auto",
comble les vides avec les valeurs par défaut et signale chaque hypothèse
dans le rapport : `⚠️ Hypothèse: [valeur]`.
```

## Exemple

```
🤔 Porthos — Clarifications pour l'audit de ~/projects/turboquant

1. 🔴 Ignorer tests/, __pycache__/ ? (défaut: OUI)
2. 🟠 Audit orienté sécurité ou qualité générale ? (défaut: les deux)
3. 🟡 Seuil de sévérité minimum ? (défaut: WARNING+)
4. ⚪ Contraintes de performance ? (défaut: NON)

Réponds avec les numéros ou "auto"
```

Réponse utilisateur : `1: oui, 2: sécurité, 3: error, 4: non`

Ou : `auto` → toutes les valeurs par défaut sont utilisées,
et le rapport contient :
```markdown
⚠️ Hypothèse: Ignorer tests/__pycache__/
⚠️ Hypothèse: Audit qualité + sécurité
⚠️ Hypothèse: Seuil WARNING+
```

## Agents couverts

| Agent | Module | Questions types |
|-------|--------|-----------------|
| 🥊 Porthos | portos_clarify() | Fichiers à ignorer, type d'audit, seuil |
| ⚔️ d'Artagnan | dartagnan_clarify() | Auto-fix scope, commits, tests |
| 📿 Aramis | aramis_clarify() | Priorité optimisation, appels dynamiques, budget |
| 👑 Athos | athos_clarify() | Pipeline complet/partiel, Cardinal activé ? |
| 🗡️ Rochefort | rochefort_clarify() | Niveau paranoïa, frameworks dynamiques |
| 🔪 Milady | milady_clarify() | Scope contre-fix, exécution tests |
| 🕯️ Comte de Wardes | comte_de_wardes_clarify() | Tolérance sur-optimisation |
| 👑 Le Cardinal | cardinal_clarify() | Confrontation, score minimum |
