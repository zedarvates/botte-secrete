---
name: nn_audit
description: Inspect micro-model training-script keywords, metadata keys, test text and source references. These heuristic labels help prioritize review; they do not verify datasets, model accuracy, executed tests or production use. Use to inspect the evidence behind a grounded, synthetic or unknown label.
---

# nn_audit — heuristic micro-model inspection

```bash
python -m skills.nn_audit.cli                 # inspect skills/botte_nn
python -m skills.nn_audit.cli <dir> --json
```

`audit_models()` inspects files without calling an LLM. Its output is evidence
for further review, with these limits:

- **data_source** — `real`, `synthetic` or `unknown` from training-script keywords.
  Real-data markers take precedence when both kinds appear. A match does not
  verify the dataset, labels, licence or collection provenance.
- **wired** and **usage** — model-name text references in production Python files,
  excluding the audit's tests and model infrastructure. A reference does not
  demonstrate an executed integration or reachable model invocation.
- **has_provenance** and **provenance_keys** — recognized metadata keys are present;
  their values and reported accuracy have not been validated.
- **has_test_guard** — the model name appears somewhere in the combined test text
  and `==` appears somewhere in that text. This does not establish a related
  model-output assertion or a passing test.
- **verdict** — heuristic `grounded`, `synthetic` or `unknown` review labels.
  Per-model **risk** is `synthetic AND wired`; summary **at_risk** counts those
  flags. Neither field proves a vulnerability or a measured model failure.

Inspect the actual training data, call sites and assertions, then run a suitable
held-out evaluation before claiming provenance, coverage or accuracy. Compare a
model with its rule-based alternative on representative tasks before deciding to
replace, connect or deploy it.

Exposed through [[llm_mcp]] as `nn_audit`; related module: [[botte_nn]]. The
reported `cloud_tokens: 0` describes this file-inspection routine. A host agent
can consume model tokens while interpreting its results.
