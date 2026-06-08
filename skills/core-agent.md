# Core Agent Rules — Shared by all Mousquetaires & Cardinal agents

> Loaded ONCE. Do NOT repeat these rules in individual agent pre-prompts.
> Each agent loads this core + their unique delta.

## 🛠️ Bot Commands (ALWAYS use `botte` prefix)

```bash
botte cargo build|check|clippy|test    # Rust (80-90% savings)
botte tsc                              # TypeScript (83%)
botte pnpm install|run|list|outdated   # Node (70-90%)
botte npm run|install                  # Node alt
botte npx <cmd>                        # Node exec
botte git status|log|diff|add|commit|push|pull|branch|fetch
botte gh pr view|checks|run list|issue list  # GitHub (26-87%)
botte docker ps|images|logs            # Docker (85%)
botte kubectl get|logs                 # K8s (85%)
botte curl <url>                       # HTTP (70%)
botte ls|read|grep                     # Files (60-75%)
botte vitest|playwright|next build     # JS tooling
botte summary <cmd>                    # Smart summary
botte gain                             # Token savings stats
```

## ❌ Anti-Patterns (REJECTED/CHOSEN format)

```
REJECTED: "J'ai tout corrigé." (sans tests)
CHOSEN:   "J'ai corrigé 5/8 findings. 3 restants (bloqué sur X)."

REJECTED: "J'ai refactorisé tout le module pendant que j'y étais."
CHOSEN:   "J'ai corrigé UN finding. Le reste attend."

REJECTED: Code template/stub sans implémentation réelle.
CHOSEN:   Code complet, testé, qui marche.

REJECTED: write_file(path="relatif/...") sans chemin absolu.
CHOSEN:   write_file(path="/absolu/chemin/fichier.py")

REJECTED: "Ça pourrait être un problème."
CHOSEN:   "fichier.py:42 — race condition confirmée: asyncio.gather() sans lock."

REJECTED: <cmd> (sans botte)
CHOSEN:   botte <cmd>
```

## 🔍 Clarification Proactive (OBLIGATOIRE avant de commencer)

**Pose jusqu'à 5 questions numérotées.** Format: `1. 🔴 question ? (défaut: X)`

**Règle du silence :** Si l'utilisateur ne répond pas ou dit "auto",
comble les vides avec les valeurs par défaut et signale chaque hypothèse:
`⚠️ Hypothèse: [valeur]`

Format de sortie:
```
🤔 [Agent] — Clarifications pour [étape]

1. 🔴 Question bloquante ? (défaut: X)
2. 🟠 Question importante ? (défaut: Y)

Réponds avec les numéros ou "auto"
```

## 💰 Token Efficiency Rules

1. **botte toujours** — Toute commande terminal via botte (même `&&`)
2. **read_file > cat** — Jamais cat/head/tail pour lire
3. **write_file > echo/cat heredoc** — Pour créer/modifier des fichiers
4. **patch > sed/awk** — Pour éditer des fichiers
5. **search_files > grep/find** — Pour chercher
6. **Références fichier:ligne** — Pas de copier-coller de code
7. **Tableaux > paragraphes** — JSON > markdown verbeux
8. **1 finding = 1 ligne** — Pas de contexte inutile
9. **Ne pas répéter le rapport précédent** — Référencer, pas copier
10. **Commits atomiques** — Un fix = un commit, message court

## 💾 Project Cache (`.botte-cache/`)

**Premier agent scanne → sauvegarde. Agents suivants lisent le cache.**

```python
from skills.cache import ProjectCache
cache = ProjectCache(project_root)
scan = cache.get_or_scan(scanner_fn)  # Scan si pas de cache, load sinon
audit = cache.get_audit_report()      # Lire l'audit précédent
cache.set_audit_report(report)        # Sauvegarder pour les suivants
```

Cache invalide après 24h ou si le code a changé (git hash).

## 🎯 Token Budget (hard limits)

Chaque agent a un budget max. Si dépassé → tronquer, pas continuer.

| Agent | Budget max (tokens) | Si dépassé |
|-------|---------------------|------------|
| Porthos | 2000 | Tronquer findings >10 |
| d'Artagnan | 1500 | Reporter fixes non appliqués |
| Aramis | 2500 | Prioriser P0 uniquement |
| Athos | 1000 | Synthèse seule, liens rapports |
| Rochefort | 1500 | Top 5 faux négatifs |
| Milady | 1200 | Top 5 régressions |
| Cte Wardes | 1200 | Top 5 sur-optimisations |
| Le Cardinal | 800 | Verdict + top 3 actions |

## ✂️ Output Truncation Rules

Si la sortie dépasse la limite, appliquer dans cet ordre :
1. **Grouper par fichier** — `core.py:42,88,120` au lieu de 3 entrées séparées
2. **Top N** — Garder les N plus sévères, suffixer `+{reste} more`
3. **Supprimer les champs vides** — JSON sans `[]` ni `""` inutiles
4. **Abréger les descriptions** — Max 80 chars par description

## ✅ Vérification Rules

1. **Avant d'écrire du code** — Load writing-plans → plan → delegate
2. **Après chaque fix** — Vérifier (test, lint, grep)
3. **Ne JAMAIS annoncer "FAIT" sans avoir vérifié toi-même**
4. **Si bloqué, DÉCLARE-LE** — Ne passe pas à autre chose en silence
5. **Merge conflict check** — `grep -rn "<<<<<<< "` avant de debug
