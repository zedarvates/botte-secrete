# 📿 Plan d'Optimisation — {{project_name}}
**Date :** {{date}}
**Optimiseur :** Aramis
**Projet :** {{project_path}}

---

## Résumé
- Tokens actuels : {{tokens_before}}/session
- Tokens optimisés : {{tokens_after}}/session
- Économie : {{tokens_saved}} ({{savings_percent}}%)
- Performance : {{perf_before}} → {{perf_after}}

---

## Optimisation des Tokens

### Skills Loading
| Métrique | Avant | Après | Économie |
|----------|-------|-------|----------|
| Skills loaded | {{skills_before}} | {{skills_after}} | {{skills_saved}} |
| Tokens/session | {{skills_tokens_before}} | {{skills_tokens_after}} | {{skills_tokens_saved}} |

### .skills-profile
```yaml
{{skills_profile_content}}
```

---

## Fichiers Gros (>1500 lignes)
| Fichier | Lignes | Modules suggérés |
|---------|--------|------------------|
{% for f in large_files %}
| {{f.file}} | {{f.lines}} | {{f.suggested_modules}} |
{% endfor %}

---

## Feature Flags Orphelins
| Flag | Fichier | Ligne | Depuis |
|------|---------|-------|--------|
{% for ff in feature_flags %}
| {{ff.name}} | {{ff.file}} | {{ff.line}} | {{ff.since}} |
{% endfor %}

---

## Hot Paths (PageRank)
| Fichier | Score | Centralité | Action |
|---------|-------|------------|--------|
{% for hp in hot_paths %}
| {{hp.file}} | {{hp.pagerank}} | {{hp.betweenness}} | {{hp.action}} |
{% endfor %}

---

## Blast Radius Élevé
| Fichier | Dépendants | Risque | Suggestion |
|---------|------------|--------|------------|
{% for br in blast_radius %}
| {{br.file}} | {{br.dependents}} | {{br.risk}} | {{br.suggestion}} |
{% endfor %}

---

## Plan d'Action Priorisé

### 🔴 Immédiat (P0)
{% for a in p0_actions %}
1. {{a.description}} — {{a.impact}}
{% endfor %}

### 🟠 Court terme (P1)
{% for a in p1_actions %}
1. {{a.description}} — {{a.impact}}
{% endfor %}

### 🟡 Moyen terme (P2)
{% for a in p2_actions %}
1. {{a.description}} — {{a.impact}}
{% endfor %}

---

## Métriques Clés
| Métrique | Avant | Après | Delta |
|----------|-------|-------|-------|
| Health score | {{health_before}} | {{health_after}} | {{health_delta}} |
| Tokens/session | {{tokens_before}} | {{tokens_after}} | {{tokens_delta}} |
| Dead code | {{dead_before}} | {{dead_after}} | {{dead_delta}} |
| Complexity | {{complexity_before}} | {{complexity_after}} | {{complexity_delta}} |
| Skills loaded | {{skills_before}} | {{skills_after}} | {{skills_delta}} |
