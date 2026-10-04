---
name: approx_spatial
layer: SENSE
description: Shadow-only deterministic spatial R&D: preserve admissible ranges, exclusions, and YES/NO/UNKNOWN/CONFLICT semantics before escalating to learned perception.
---

# approx_spatial

Cheap spatial reasoning experiments for issue #137.

Current scope is **0A1 only**: deterministic fixtures and proposition semantics.
It does not control hardware, estimate real camera depth, call a model, or activate
a runtime route.

```bash
python -m skills.approx_spatial.benchmark
python -m skills.approx_spatial.benchmark --json
python -m pytest skills/approx_spatial/test_approx_spatial.py -q
```

Principles:

- measurement and decision stay separate;
- `UNKNOWN` is not `NO`;
- failed validity guards abstain;
- contradictory admissible constraints produce `CONFLICT`;
- intervals/exclusions are preserved instead of inventing a midpoint;
- reports contain deterministic fixture/result hashes and no timestamp.
