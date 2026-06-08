# ⚔️ Rapport de Fix — {{project_name}}
**Date :** {{date}}
**Développeur :** d'Artagnan
**Audit de référence :** {{audit_report}}

---

## Résumé
- Findings traités : {{fixed_count}}/{{total_findings}}
- Fichiers modifiés : {{modified_files}}
- Tests passent : {{tests_status}}
- Commits : {{commit_count}}

---

## Corrections Appliquées

{% for fix in fixes %}
### Finding: {{fix.original_finding}}
- **Fichier :** `{{fix.file}}:{{fix.line}}`
- **Action :** {{fix.action}}
- **Vérification :** {{fix.verification}}
- **Status :** {{fix.status}}
{% endfor %}

---

## Fichiers Modifiés
| Fichier | Changements | Commit |
|---------|-------------|--------|
{% for f in modified %}
| {{f.file}} | {{f.changes}} | `{{f.commit}}` |
{% endfor %}

---

## Tests
```bash
{{test_command}}
```
```
{{test_output}}
```

---

## Restant (non traité)
{% for rem in remaining %}
- [ ] `{{rem.file}}:{{rem.line}}` — {{rem.finding}} ({{rem.reason}})
{% endfor %}
