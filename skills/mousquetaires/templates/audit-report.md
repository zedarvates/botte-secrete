# 🔬 Rapport d'Audit — {{project_name}}
**Date :** {{date}}
**Auditeur :** Porthos
**Projet :** {{project_path}}

---

## Score de Santé : {{health_score}}/100 ({{grade}})

## Résumé
- Fichiers analysés : {{total_files}}
- Lignes de code : {{total_lines}}
- Trouvé : {{total_findings}} findings
  - 🔴 Critique : {{critical_count}}
  - 🟠 Erreur : {{error_count}}
  - 🟡 Warning : {{warning_count}}
  - ℹ️ Info : {{info_count}}

---

## Findings par Sévérité

### 🔴 Critique ({{critical_count}})
{% for f in critical %}
- [ ] `{{f.file}}:{{f.line}}` — {{f.description}}
{% endfor %}

### 🟠 Erreur ({{error_count}})
{% for f in errors %}
- [ ] `{{f.file}}:{{f.line}}` — {{f.description}}
{% endfor %}

### 🟡 Warning ({{warning_count}})
{% for f in warnings %}
- [ ] `{{f.file}}:{{f.line}}` — {{f.description}}
{% endfor %}

### ℹ️ Info ({{info_count}})
{% for f in infos %}
- [ ] `{{f.file}}:{{f.line}}` — {{f.description}}
{% endfor %}

---

## Code Mort ({{dead_code_count}})
| Fichier | Symbole | Ligne | Type |
|---------|---------|-------|------|
{% for dc in dead_code %}
| {{dc.file}} | {{dc.symbol}} | {{dc.line}} | {{dc.type}} |
{% endfor %}

---

## Duplication ({{duplication_count}})
| Fichier A | Fichier B | Similarité | Lignes |
|-----------|-----------|------------|--------|
{% for dup in duplications %}
| {{dup.file_a}} | {{dup.file_b}} | {{dup.similarity}}% | {{dup.lines}} |
{% endfor %}

---

## Complexité ({{complexity_count}})
| Fonction | Fichier | Complexité | Nesting |
|----------|---------|------------|---------|
{% for c in complexities %}
| {{c.function}} | {{c.file}} | {{c.complexity}} | {{c.nesting}} |
{% endfor %}

---

## Violations d'Architecture ({{boundary_count}})
| Fichier | Violation | Ligne |
|---------|-----------|-------|
{% for b in boundaries %}
| {{b.file}} | {{b.violation}} | {{b.line}} |
{% endfor %}

---

## Secrets Détectés ({{secret_count}})
| Fichier | Type | Sévérité | Pattern |
|---------|------|----------|---------|
{% for s in secrets %}
| {{s.file}} | {{s.type}} | {{s.severity}} | {{s.pattern}} |
{% endfor %}

---

## Feature Flags ({{feature_flag_count}})
| Flag | Fichier | Ligne | Type |
|------|---------|-------|------|
{% for ff in feature_flags %}
| {{ff.name}} | {{ff.file}} | {{ff.line}} | {{ff.type}} |
{% endfor %}

---

## Recommandations
{% for rec in recommendations %}
{{loop.index}}. [{{rec.priority}}] {{rec.description}}
{% endfor %}
