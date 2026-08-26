---
license: mit
library_name: generic
tags:
- tiny-neural-network
- micro-ml
- rust
- numpy
- local-first
- botte-secrete
- agent-routing
- edge-inference
---

# Botte Nano-NN — tiny classifiers for agent routing

MIT-licensed feed-forward classifiers used as **advisory hints** by
[Botte Secrète](https://github.com/zedarvates/botte-secrete), a local-first
control plane for AI coding agents. These are classifiers, not language models:
they do not generate text and a prediction is never proof that a task succeeded.

## Current status

The authoritative source currently wires **11 micro-NN predictors**. Four have
reproducible training or distillation paths and guards; seven remain
observation-only until label provenance, temporal evaluation, calibration,
drift detection, and rollback are complete.

The model-by-model status is maintained in the
[grounding roadmap](https://github.com/zedarvates/botte-secrete/blob/main/docs/plans/2026-08-06_micro-nn-grounding-roadmap.md).
Run the audit instead of inferring maturity from the presence of a weight file:

```bash
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete
python -m skills.auto_router.checkup_belt2
python -m skills.nn_audit.cli skills/botte_nn --json
python -m skills.botte_nn.cli list
```

## Where it is used

- [Botte Secrète micro-NN belt](https://github.com/zedarvates/botte-secrete/tree/main/skills/botte_nn)
- [Botte Secrète router integration](https://github.com/zedarvates/botte-secrete/tree/main/skills/auto_router)
- [MCP gateway](https://github.com/zedarvates/botte-secrete/tree/main/skills/mcp_gateway)

## Inference

Python inference reads the JSON weights directly. The optional Rust binary uses
the same format.

```bash
python -m skills.botte_nn.cli predict \
  skills/botte_nn/models/effort_classifier.json \
  --input 0.1 0.2 0.8 0.0
```

Feature order and normalization are part of each model's contract. Do not pass
anonymous vectors copied from an unrelated task; use the named extractors in
[`features.py`](https://github.com/zedarvates/botte-secrete/blob/main/skills/botte_nn/features.py).

## Intended use and limits

Use the models for cheap local comparisons and shadow routing experiments.
Low-confidence predictions must abstain or escalate. Do not use them as safety,
legal, licensing, publishing, or deployment gates. Bundled fixtures test
regressions; they do not prove production generalization or a universal token
saving percentage.

## Reproducibility and licence

Source, training code, feature contracts, tests, and issues:
[zedarvates/botte-secrete](https://github.com/zedarvates/botte-secrete).

Released under the [MIT License](https://github.com/zedarvates/botte-secrete/blob/main/LICENSE).
