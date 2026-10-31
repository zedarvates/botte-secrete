---
name: approx_spatial
layer: SENSE
description: Shadow-only deterministic spatial R&D: preserve admissible ranges, exclusions, and YES/NO/UNKNOWN/CONFLICT semantics before escalating to learned perception.
---

# approx_spatial

Cheap spatial reasoning experiments for issue #137.

Current scope is **0A1 and 0A2**: deterministic fixtures, proposition semantics,
and calibrated parallax range intervals from caller-supplied measurements.
It does not control hardware, match camera features, call a model, or activate a
runtime route.

```bash
python -m skills.approx_spatial.benchmark
python -m skills.approx_spatial.benchmark --json
python -m skills.approx_spatial.test_approx_spatial
python -m skills.approx_spatial.test_parallax
```

Principles:

- measurement and decision stay separate;
- `UNKNOWN` is not `NO`;
- failed validity guards abstain;
- bounds and thresholds require finite numbers; strings and booleans are rejected;
- parallax guard thresholds must be finite and non-negative;
- contradictory admissible constraints produce `CONFLICT`;
- intervals/exclusions are preserved instead of inventing a midpoint;
- reports contain deterministic fixture/result hashes and no timestamp.
