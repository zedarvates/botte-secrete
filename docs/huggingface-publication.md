# Hugging Face publication checklist

Three MIT repositories were verified under the `zedgamer` namespace:

| Package | Hugging Face repository | Public payload |
|---|---|---|
| Botte micro-NN belt | [`zedgamer/botte-nano-nn`](https://huggingface.co/zedgamer/botte-nano-nn) | Corrected card; weights only after source/hash audit |
| CogniARC micro-NN | [`zedgamer/cogniarc-nano-nn`](https://huggingface.co/zedgamer/cogniarc-nano-nn) | Corrected card; experimental classifiers and limitations |
| Asset Quality Memory | [`zedgamer/asset-quality-memory-knn`](https://huggingface.co/zedgamer/asset-quality-memory-knn) | Card and source links; never a private memory ledger |

All three URLs now resolve. Before replacing weights, compare hashes and
the model-specific training provenance. The current Hub Botte snapshot differs
from the authoritative source and contains only part of the 11-model inventory.

The machine-readable
[`model-snapshot.json`](../distribution/huggingface/micro-nn/model-snapshot.json)
records the immutable Hub revision and both SHA-256 inventories. Its current
`publish_weights_allowed` value is `false`: none of the four shared JSON files
matches source, two Hub files are absent from source, seven source files are
absent from the Hub, and eight source models do not yet pass the strict
`nn_audit` grounding gate.

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
python -m skills.hf_provenance.cli /path/to/downloaded/models \
  --hub-revision <immutable-hub-sha> \
  --source-revision <git-sha>
```

The final command must exit `0`. Exit `2` is a hard publication block; a
filename match alone is never evidence that two weight files are equivalent.

The Botte Secrète and CogniARC GitHub READMEs should link back to their resolved
Hub repositories. Never upload
`.botte/`, secrets, machine configuration, unverified training data, or assets
whose licence and provenance are unknown.
