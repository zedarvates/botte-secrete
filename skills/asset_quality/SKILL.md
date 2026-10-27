---
name: asset-quality
description: Evaluate generated images, textures, meshes, animations, and Godot packages with deterministic gates followed by an explainable family-local k-NN memory.
license: MIT
---

# Asset Quality Memory

Asset Quality Memory is a zero-cloud, standard-library baseline for Asset
Factory QA. It is deliberately **shadow-only**: it explains `FAIL`, `UNCERTAIN`,
`PASS`, or `PASS_ROBUST`, but never imports, publishes, or activates an asset.

## Decision order

1. Decode, manifest, SHA-256/size, and licence checks.
2. Family-specific deterministic checks.
3. k-NN over externally verified assets from the same family only.
4. Abstention when fewer than three comparable examples exist.
5. A future micro-NN is considered only after beating this baseline on a
   temporal holdout without reducing quality.

Supported families are `image`, `texture`, `mesh`, `animation`, and `godot`.
Their feature schemas are intentionally separate; a mesh can never become a
neighbor of an image.

## Commands

```bash
botte asset-qa status . --json
botte asset-qa evaluate asset-report.json --project . --json
botte asset-qa record asset-report.json --project . \
  --verdict pass --verified-by tests:asset-harness --evidence ci:asset-142
```

The report contains `family`, `sha256`, `size_bytes`, `checks`, and normalized
`features`. See the [JSON schema](../../docs/schemas/asset-quality-report.schema.json)
and `examples/asset-quality/mesh-report.json` for a complete input.
Operational memory is written to `.botte/asset-quality.jsonl`; local paths and
raw asset bytes are never stored.

This implementation runs on CPU and mono-GPU machines. An RTX 3060 or other GPU
may generate embeddings upstream later, but it is not required or trusted by
the integrity gates.
