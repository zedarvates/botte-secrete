---
license: mit
library_name: botte-secrete
tags:
- tiny-neural-network
- local-first
- routing
- edge-ai
- cpu
---

# Botte Secrète Micro-NN Belt

Eleven tiny feed-forward classifiers used as **advisory routing hints** inside
[Botte Secrète](https://github.com/zedarvates/botte-secrete). They are not
language models and do not generate content.

## Grounding status

- Four models have reproducible distillation/training paths and guards.
- Seven predictors remain observation-only while their label provenance,
  temporal evaluation, calibration, drift, and rollback gates are completed.
- Low-confidence output abstains. A prediction is never proof that a task
  succeeded.

The authoritative, model-by-model maturity table is the
[Micro-NN Grounding Roadmap](https://github.com/zedarvates/botte-secrete/blob/main/docs/plans/2026-08-06_micro-nn-grounding-roadmap.md).

## Use from the source repository

```bash
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete
python -m skills.auto_router.checkup_belt2
python -m skills.nn_audit.cli skills/botte_nn --json
python -m skills.botte_nn.cli list
```

Weights are JSON files under `skills/botte_nn/models/`; Python inference is
available without compiling Rust. The optional Rust implementation reads the
same format.

## Intended use and limits

Use these classifiers to compare cheap local routing hypotheses in shadow mode.
Do not use them as safety, legal, licensing, publishing, or deployment gates.
Metrics from the bundled synthetic corpus are regression checks, not general
production-quality claims.

Source and issue tracker:
[zedarvates/botte-secrete](https://github.com/zedarvates/botte-secrete).

## Licence

MIT. See the source repository's
[LICENSE](https://github.com/zedarvates/botte-secrete/blob/main/LICENSE).
