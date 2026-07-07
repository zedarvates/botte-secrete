# Plan de Visibilité — botte-secrete
Basé sur l'audit GLM-5.2 + état réel du repo (27 juin 2026)

## État actuel
- ✅ Repo public, 5 tags (v1.0.0→v1.4.0), 2 CI workflows
- ✅ 459 tests verts, stdlib pur, 50+ skills
- ❌ Pas de GPG, pas de SECURITY.md, pas de LICENSE fichier
- ❌ README sans section "confiance", pas de smoke test
- ❌ Profil GitHub vide de bio utile, 6 followers
- ❌ Pas de présence Reddit/X

---

## Phase 1 — Crédibilité technique (1h)
Ce qui fait qu'un agent/contributeur fait confiance au premier coup d'œil.

### 1.1 Ajouter LICENSE (MIT)
```bash
curl -s https://api.github.com/licenses/mit | jq -r '.body' > LICENSE
```
Manquant actuellement — README dit MIT mais pas de fichier.

### 1.2 Ajouter SECURITY.md
Politique de signalement : email, réponse sous 48h, pas de fork.

### 1.3 Ajouter CONTRIBUTING.md
Comment proposer une PR, conventions de commit, tests requis.

### 1.4 README — section "Ce que ça modifie sur ta machine"
```
## 🔒 Impact sur ton système
- `.mcp.json` — ajoute 5 outils MCP (auto_route, local_chat, fusion, etc.)
- Pas d'installation système, pas de cron, pas de service
- Pas d'appels réseau sortants (sauf si tu configures un provider cloud)
- Vérifiable : `python -m skills.llm_mcp.server --help`
```

### 1.5 README — smoke test
```
## ✅ Smoke test
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete
python -m skills.llm_backends.cli scan          # détecte les LLM locaux
python -m skills.auto_router.cli route "hello"  # 0 token, décision locale
python scripts/run_tests.py                     # 459 tests verts
```

---

## Phase 2 — Signatures & Intégrité (2h)
Preuve que le code n'a pas été falsifié entre le push et le clone.

### 2.1 Configurer GPG
```bash
gpg --full-generate-key  # ou importer une clé existante
git config --global user.signingkey <key-id>
git config --global commit.gpgsign true
```

### 2.2 Signer les tags de release
```bash
git tag -s v1.4.1 -m "Signed release v1.4.1"
git push origin v1.4.1
git tag --verify v1.4.1
```

### 2.3 Ajouter SHA256SUMS aux releases
Pour chaque release, générer :
```bash
find skills/ -type f -exec sha256sum {} \; > SHA256SUMS
gpg --armor --detach-sign SHA256SUMS  # SHA256SUMS.asc
```

---

## Phase 3 — Visibilité publique (3h)
Faire savoir que le repo existe.

### 3.1 README — section "Adoption"
```markdown
## 📊 Chiffres clés
- **459** tests, 0 échecs
- **50+** skills, **6** micro-NN
- **~65%** d'économie de tokens
- **0** dépendances ML lourdes (stdlib + numpy)
```

### 3.2 Post Reddit (r/LocalLLaMA)
Charger la skill `botte-secrete-pitch` et poster. Template déjà prêt.

### 3.3 Post X/Twitter
Fil de 6 tweets (template prêt).

### 3.4 Profil GitHub
- Mettre une vraie bio : "Token optimization toolkit · Local AI agent platform · MIT"
- Ajouter twitter/bio professionnelle
- Épingler le repo en haut du profil

### 3.5 Badges README
Ajouter : licence MIT, Python 3.10+, PRs welcome, GitHub stars

---

## Phase 4 — Communauté (4h)
Faire revenir les gens.

### 4.1 GitHub Discussions
Activer les Discussions sur le repo pour les questions/Q&A.

### 4.2 Répondre aux Issues
Si quelqu'un ouvre une issue, réponse < 24h.

### 4.3 Démo vidéo
Créer une courte vidéo (StoryCore?) montrant :
- `botte gain` → économie de tokens
- `python -m skills.auto_router.cli route "..."` → 0 token
- `botte cargo test` → compression 90%

### 4.4 Démos régulières
Posts hebdomadaires "Cette semaine dans botte-secrete" (nouveaux modèles, améliorations)

---

## Priorité recommandée
1. **LICENSE + SECURITY.md** (30 min) — prérequis confiance
2. **README sections confiance** (30 min) — visible tout de suite
3. **Post Reddit** (15 min) — premier afflux de visiteurs
4. **GPG + commits signés** (1h) — crédibilité technique long terme
5. **Profil GitHub** (15 min) — première impression
6. **Post X** (15 min) — deuxième canal
7. **GitHub Discussions** (10 min) — rétention

## Métriques de succès
- **Avant :** 6 followers, 0 posts
- **Après Phase 1-2 :** README vérifiable, builds signés
- **Après Phase 3 :** 1 post Reddit, 1 thread X, profil rempli
- **Objectif mois+1 :** +20 stars, +5 forks, 1 contribution externe
