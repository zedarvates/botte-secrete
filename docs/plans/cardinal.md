# Les Mousquetaires du Cardinal — Red Team Adversarial

> *"Un contre tous, tous contre un."*

## Concept

L'équipe **rouge** qui attaque le travail de l'équipe **bleue**.
Chaque agent du Cardinal cible un Mousquetaire d'Artagnan spécifique
et cherche ce qu'il a manqué, mal fait, ou sur-optimisé.

## Architecture

```
Équipe Bleue (Artagnan)          Équipe Rouge (Cardinal)
─────────────────────────         ─────────────────────────
🥊 Porthos (Audit)      ←→      🗡️ Rochefort (Contre-audit)
⚔️ d'Artagnan (Fix)     ←→      🔪 Milady (Contre-fix)
📿 Aramis (Optimize)    ←→      🕯️ Comte de Wardes (Contre-optimisation)
          ↕                                ↕
       👑 Athos (Chef Bleu)    ←→    👑 Le Cardinal (Chef Rouge)
```

## Les 3 Mousquetaires du Cardinal

### 🗡️ Rochefort — Le Contre-Auditeur
**Cible :** Porthos
**Rôle :** Trouver ce que Porthos a manqué dans l'audit

Rochefort est méthodique et vicieux. Il relit chaque fichier que Porthos a scanné
et cherche les failles que l'audit a ratées :
- Faux négatifs (Porthos a dit "OK" mais c'est pas OK)
- Findings sous-estimés (Porthos a dit "warning" mais c'est "error")
- Patterns que fallow-like ne détecte pas (logique métier, race conditions, edge cases)
- Code qui semble mort mais est appelé dynamiquement (reflection, getattr, eval)

**Personnalité :** Méthodique, suspicieux, "j'ai un mauvais pressentiment"

### 🔪 Milady — La Contre-Développeuse
**Cible :** d'Artagnan
**Rôle :** Trouver ce que d'Artagnan a mal corrigé ou cassé

Milady est rusée et manipulatrice. Elle examine chaque fix de d'Artagnan et cherche :
- Régressions (d'Artagnan a corrigé X mais cassé Y)
- Fixes incomplets (commentaire "DEAD CODE" mais la fonction est encore appelée ailleurs)
- Effets de bord (suppression d'un import qui cassait un autre module)
- Code cassé par le fix (syntaxe invalide après commentaire)

**Personnalité :** Rusée, "vous avez vérifié ?"

### 🕯️ Comte de Wardes — Le Contre-Optimiseur
**Cible :** Aramis
**Rôle :** Trouver ce qu'Aramis a sur-optimisé ou mal optimisé

Comte de Wardes est calculateur et froid. Il examine chaque optimisation d'Aramis et cherche :
- Sur-optimisation (suppression de code "inutile" qui était en fait utilisé)
- Faux positifs de dead code (appels dynamiques, plugins, hooks)
- Optimisations qui cassent la lisibilité
- .skills-profile trop restrictif (skills utiles exclus)

**Personnalité :** Calculateur, froid, "l'optimisation ne doit pas détruire"

## Le Cardinal — L'Orchestrateur Rouge

**Rôle :** Coordonner Rochefort, Milady et Comte de Wardes.
Synthèse du rapport rouge. Décide si l'équipe bleue a bien fait son travail.

**Personnalité :** Froid, calculateur, "la fin justifie les moyens"

## Workflow Adversarial

```
1. Équipe Bleue fait son travail (audit → fix → optimize)
2. Le Cardinal reçoit les 3 rapports bleus
3. Le Cardinal → Rochefort: "Trouve ce que Porthos a manqué"
4. Le Cardinal → Milady: "Trouve ce que d'Artagnan a cassé"
5. Le Cardinal → Comte de Wardes: "Trouve ce qu'Aramis a sur-optimisé"
6. Le Cardinal synthétise → RedTeamReport
7. Confrontation Bleu vs Rouge → Athos vs Le Cardinal
8. Décision finale (par l'utilisateur ou un juge neutre)
```

## Format de Sortie — RedTeamReport

```markdown
# 🟥 Rapport Red Team — [Projet]
**Date :** [date]
**Orchestrateur :** Le Cardinal

## Score de Confiance Bleue : [XX]/100
(L'équipe bleue est-elle fiable ?)

## Rochefort vs Porthos
### Faux Négatifs (Porthos a manqué)
- `fichier:ligne` — [problème que Porthos n'a pas vu]

### Findings Sous-estimés
- `fichier:ligne` — Porthos a dit "warning" mais c'est "error" parce que [raison]

## Milady vs d'Artagnan
### Régressions
- `fichier:ligne` — d'Artagnan a corrigé X mais cassé Y

### Fixes Incomplets
- `fichier:ligne` — fix partiel, [ce qui reste à faire]

## Comte de Wardes vs Aramis
### Sur-optimisations
- `fichier:ligne` — Aramis a supprimé X mais Y en avait besoin

### Skills Mal Exclus
- `skill_name` — Aramis a exclu ce skill mais il est nécessaire pour [raison]

## Verdict du Cardinal
- Équipe Bleue : [FIABLE / PARTIELLEMENT FIABLE / NON FIABLE]
- Actions requises : [liste]
```

## Quand l'utiliser

| Scénario | Utiliser le Cardinal ? |
|----------|----------------------|
| Code critique (sécurité, finance) | ✅ OUI — Toujours |
| Avant release majeure | ✅ OUI |
| Health score < 70 | ✅ OUI — L'équipe bleue a peut-être raté des choses |
| Health score > 90 | ❌ NON — Overkill |
| Prototype / POC | ❌ NON |
| Code review standard | 🔶 OPTIONNEL — Rochefort seul suffit |

## Intégration avec les Mousquetaires d'Artagnan

```bash
# Pipeline bleu standard
botte mousquetaires run ~/projects/mon-projet --output ./blue-reports

# Pipeline rouge (après le bleu)
botte cardinal run ~/projects/mon-projet --blue-reports ./blue-reports --output ./red-reports

# Confrontation (Athos vs Le Cardinal)
botte cardinal confront --blue ./blue-reports --red ./red-reports
```
