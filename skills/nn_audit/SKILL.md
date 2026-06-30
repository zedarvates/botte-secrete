---
name: nn_audit
description: Audit the micro-NNs — is each model grounded in REAL data, or a synthetic copy of a hand-coded rule? Scans skills/botte_nn and reports, per model, the training data source (real/synthetic/unknown), whether the model file records provenance (trained_on/eval_accuracy), whether a test guards a real-world output, and a grounded/synthetic verdict. Deterministic, 0 cloud tokens. Use to tell which learned components are real vs placeholder, and which should be grounded or replaced by the rule they imitate.
---

# nn_audit — grounded NNs, or synthetic copies of rules?

A learned component only earns its place if it's trained on **real data a rule
can't capture**. A net trained on `np.random` + hand-coded labels just
approximates a deterministic function we already wrote — strictly worse than the
rule (adds error + opacity, learns nothing). This audits which micro-NNs are real.

```bash
python -m skills.nn_audit.cli                 # audit skills/botte_nn
python -m skills.nn_audit.cli <dir> --json
```

Per model it reports:
- **data_source** — `real` | `synthetic` | `unknown`, inferred from the training
  script's content (distill/corpus/labelled → real; `np.random` → synthetic).
- **has_provenance** — does the `.json` record `trained_on` / `eval_accuracy` / `data`?
- **has_test_guard** — does a test assert a specific real-world output for it?
- **verdict** — `grounded` | `synthetic — mimics a hand rule` | `unknown`, plus an
  `at_risk` flag (synthetic + no guard).

The fix for a synthetic model is binary: **ground it** on real data (distillation
/ active-learning, like `error_classifier`) **or replace it** with the rule it
imitates. Exposed via [[llm_mcp]] as `nn_audit`; pairs with [[botte_nn]] and the
deterministic-vs-learned discussion. Pure file inspection, 0 cloud tokens.
