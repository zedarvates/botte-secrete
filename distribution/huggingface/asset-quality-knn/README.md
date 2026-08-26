---
license: mit
library_name: botte-secrete
tags:
- knn
- asset-quality
- explainable-ai
- local-first
- 3d
- godot
---

# Asset Quality Memory k-NN

An explainable, zero-cloud k-nearest-neighbor baseline for Asset Factory QA,
implemented in
[Botte Secrète](https://github.com/zedarvates/botte-secrete/tree/main/skills/asset_quality).

## What it does

1. Runs deterministic integrity, licence, manifest, SHA-256, and size checks.
2. Applies family-specific checks for images, textures, meshes, animations, or
   Godot packages.
3. Searches only externally verified neighbors from the same asset family.
4. Returns `FAIL`, `UNCERTAIN`, `PASS`, or `PASS_ROBUST`, with neighbor IDs.
5. Abstains when fewer than three comparable examples exist.

It is shadow-only and cannot import, activate, or publish an asset. CPU is
enough; a GPU can generate upstream features but cannot bypass hard checks.

## Quick start

```bash
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete
python -m skills.asset_quality.cli evaluate \
  examples/asset-quality/mesh-report.json --json
python -m skills.asset_quality.test_asset_quality
```

Verified memories remain project-local in `.botte/asset-quality.jsonl`. Do not
upload that file: it may reveal operational fingerprints or evaluation history.
This Hub repository distributes the implementation contract and documentation,
not a user's private neighbor index.

## Intended use and limits

This baseline helps decide whether a specialized micro-NN is justified. Promote
a learned model only if it beats k-NN on a representative temporal holdout
without weakening deterministic checks or verified quality.

Source and issue tracker:
[zedarvates/botte-secrete](https://github.com/zedarvates/botte-secrete).

## Licence

MIT. See the source repository's
[LICENSE](https://github.com/zedarvates/botte-secrete/blob/main/LICENSE).
