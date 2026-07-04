---
name: decision-ladder
description: "Ponytail-inspired YAGNI enforcement — climb the decision ladder before writing any code. stdlib → regex → existing module → new code."
version: 1.0.0
trigger_keywords:
  - "decision ladder"
  - "ponytail"
  - "yagni"
  - "lazy dev"
  - "over-engineering"
---

# Decision Ladder

Ponytail-inspired YAGNI enforcement for botte-secrete. Before writing ANY code, climb this ladder. Each rung that passes saves the cost of every rung above it.

## The Ladder

1. **stdlib** — Is this already in Python's standard library? (os, pathlib, json, re, ast, sqlite3, http, etc.)
2. **regex_oneliner** — Can a regex, string method, or one-liner do it? No function needed.
3. **existing_module** — Does an existing botte skill already handle this? Reuse > rebuild.
4. **new_code** — No simpler alternative exists. Write the minimal implementation.

## Usage

```python
from skills.decision_ladder.ladder import climb, audit_task_list

# Single task
result = climb("extract function names from a Python file")
# → LadderResult(rung="stdlib", solution="ast module (ast.parse/walk)", saved_lines=15)

# Audit a task list
report = audit_task_list([
    "parse JSON config",
    "design auth middleware",
    "count word frequency in text",
    "strip HTML tags from string",
    "implement custom OR-Tools solver",
])
# → avoidable_pct: 80%, lines_saved: 85
```

## Integration

Add to workflow-check as a pre-code hook. See `hook.py`.

## Metrics

Tracks:
- % of tasks that could be avoided (stdlib, regex, existing module)
- Estimated lines saved per task
- Confidence score per suggestion
