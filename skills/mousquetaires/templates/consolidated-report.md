# 👑 Rapport Consolidé — {{project_name}}
**Date :** {{date}}
**Orchestrateur :** Athos
**Pipeline :** Porthos → d'Artagnan → Aramis

---

## Score Global : {{global_score}}/100

## Synthèse des Mousquetaires

### 🥊 Porthos (Audit)
- Health score : {{audit.health_score}}/100
- Findings : {{audit.total_findings}} total
  - 🔴 {{audit.critical}} critique
  - 🟠 {{audit.errors}} erreur
  - 🟡 {{audit.warnings}} warning
- Top 3 problèmes :
  1. {{audit.top_1}}
  2. {{audit.top_2}}
  3. {{audit.top_3}}

### ⚔️ d'Artagnan (Fix)
- Findings traités : {{fix.fixed_count}}/{{fix.total_findings}}
- Fichiers modifiés : {{fix.modified_files}}
- Tests : {{fix.tests_status}}
- Commits : {{fix.commit_count}}

### 📿 Aramis (Optimisation)
- Tokens économisés : {{opt.tokens_saved}} ({{opt.savings_percent}}%)
- Skills loaded : {{opt.skills_before}} → {{opt.skills_after}}
- Quick wins :
  1. {{opt.quick_win_1}}
  2. {{opt.quick_win_2}}

---

## Plan d'Action Consolidé

### 🔴 Immédiat (P0)
{% for a in p0 %}
1. {{a}}
{% endfor %}

### 🟠 Court terme (P1)
{% for a in p1 %}
1. {{a}}
{% endfor %}

### 🟡 Moyen terme (P2)
{% for a in p2 %}
1. {{a}}
{% endfor %}

---

## Métriques Clés
| Métrique | Avant | Après | Delta |
|----------|-------|-------|-------|
| Health score | {{metrics.health_before}} | {{metrics.health_after}} | {{metrics.health_delta}} |
| Tokens/session | {{metrics.tokens_before}} | {{metrics.tokens_after}} | {{metrics.tokens_delta}} |
| Dead code | {{metrics.dead_before}} | {{metrics.dead_after}} | {{metrics.dead_delta}} |
| Complexity | {{metrics.complexity_before}} | {{metrics.complexity_after}} | {{metrics.complexity_delta}} |
| Skills loaded | {{metrics.skills_before}} | {{metrics.skills_after}} | {{metrics.skills_delta}} |

---

## Rapports Détaillés
- 🔬 Audit : `{{paths.audit_report}}`
- ⚔️ Fix : `{{paths.fix_report}}`
- 📿 Optimisation : `{{paths.optimization_plan}}`
