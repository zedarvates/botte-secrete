# Hugging Face publication checklist

Two existing MIT repositories were verified under the `zedgamer` namespace.
The Asset Quality Memory card is staged as a third, not-yet-created repository:

| Package | Hugging Face repository | Public payload |
|---|---|---|
| Botte micro-NN belt | [`zedgamer/botte-nano-nn`](https://huggingface.co/zedgamer/botte-nano-nn) | Corrected card; weights only after source/hash audit |
| CogniARC micro-NN | [`zedgamer/cogniarc-nano-nn`](https://huggingface.co/zedgamer/cogniarc-nano-nn) | Corrected card; experimental classifiers and limitations |
| Asset Quality Memory | Proposed `zedgamer/asset-quality-memory-knn` | Card, reference implementation, example and tests; never a private memory ledger |

The two existing URLs now resolve. Before replacing weights, compare hashes and
the model-specific training provenance. The current Hub Botte snapshot differs
from the authoritative source and contains only part of the 11-model inventory.

## Safe update sequence

```bash
hf auth whoami
hf models list --author zedgamer
hf upload zedgamer/botte-nano-nn \
  distribution/huggingface/micro-nn/README.md README.md
hf upload zedgamer/cogniarc-nano-nn \
  distribution/huggingface/cogniarc-nano-nn/README.md README.md
hf upload zedgamer/asset-quality-memory-knn \
  distribution/huggingface/asset-quality-knn/README.md README.md
```

Before uploading weights, run:

```bash
python -m skills.auto_router.checkup_belt2
python -m skills.nn_audit.cli skills/botte_nn --json
python -m skills.asset_quality.test_asset_quality
```

The Botte Secrète and CogniARC GitHub READMEs should link back to their resolved
Hub repositories. Never upload
`.botte/`, secrets, machine configuration, unverified training data, or assets
whose licence and provenance are unknown.
