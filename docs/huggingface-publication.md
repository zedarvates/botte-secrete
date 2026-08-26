# Hugging Face publication checklist

Two MIT cards are staged under `distribution/huggingface/`:

| Package | Proposed repository slug | Public payload |
|---|---|---|
| Micro-NN belt | `botte-secrete-micro-nn-belt` | Card plus audited JSON weights and feature contract |
| Asset Quality Memory | `asset-quality-memory-knn` | Card, reference implementation, example and tests; never a private memory ledger |

Do not publish until the exact Hugging Face namespace and the two existing
repository URLs have been verified. The GitHub README must link to the final Hub
URLs only after they resolve.

## Safe update sequence

```bash
hf auth whoami
hf models list --author <verified-namespace>
hf upload <verified-namespace>/botte-secrete-micro-nn-belt \
  distribution/huggingface/micro-nn/README.md README.md
hf upload <verified-namespace>/asset-quality-memory-knn \
  distribution/huggingface/asset-quality-knn/README.md README.md
```

Before uploading weights, run:

```bash
python -m skills.auto_router.checkup_belt2
python -m skills.nn_audit.cli skills/botte_nn --json
python -m skills.asset_quality.test_asset_quality
```

Then add a small “Hugging Face” section to the GitHub README with both resolved
URLs and add the Botte Secrète source link to both Hub cards. Never upload
`.botte/`, secrets, machine configuration, unverified training data, or assets
whose licence and provenance are unknown.
