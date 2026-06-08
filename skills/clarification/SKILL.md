# Clarification Proactive
Up to 5 numbered questions before starting work. Silence = auto-fill with defaults.

**Trigger:** At the START of every agent's workflow (OBLIGATOIRE).

**Pattern:**
```
🤔 [Agent] — Clarifications pour [étape]
1. 🔴 Question bloquante ? (défaut: X)
2. 🟡 Question secondaire ? (défaut: Y)
Réponds avec les numéros ou "auto"
```

**Module:** `skills/clarification`
**Generators:** portos_clarify(), dartagnan_clarify(), aramis_clarify(), etc.
**Rule:** Silence = auto → fill defaults → flag `⚠️ Hypothèse: [valeur]`
