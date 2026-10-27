---
name: hf_provenance
description: Compare a downloaded Hugging Face JSON-weight snapshot with the authoritative Botte micro-NN source. Produces SHA-256 inventories and blocks publication on missing, extra, changed, invalid, or unproven model files. Offline and dependency-free.
---

# Hugging Face provenance gate

Download the Hub JSON files into a bounded temporary directory, then run:

```bash
python -m skills.hf_provenance.cli /tmp/botte-hub-models \
  --hub-revision <immutable-hub-sha> \
  --source-revision <git-sha> \
  --output distribution/huggingface/micro-nn/model-snapshot.json
```

Exit code `0` means the complete inventories, SHA-256 digests, JSON validity,
and source provenance checks all pass. Exit code `2` is a publication block.
Never replace Hub weights by treating a filename match as proof.
