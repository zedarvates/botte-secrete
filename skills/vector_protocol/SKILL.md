---
name: vector_protocol
description: Encode structured findings into 24 numeric positions and search them in the in-memory VectorStore. This experimental codec uses fixed features, not learned embeddings; decoding cannot recover original paths or descriptions. Preserve the original findings and measure results before integration.
---

# Vector Agent Protocol — experimental finding codec

`skills.vector_protocol` encodes severity, type, four bytes of a file-reference
hash, a line number and an action in 24 numeric positions. These are fixed
structured features, not learned semantic embeddings.

`VectorStore` keeps vectors and payloads in process memory and searches by cosine
similarity. `AgentVectorBridge` uses that store. A Qdrant backend, persistent
storage and a deployed multi-agent pipeline are not implemented by this module.

```python
from skills.vector_protocol import encode_finding, decode_vector

original = {"f": "file.py:42", "s": "err", "t": "dead", "a": "review",
            "d": "Check the unused function"}
vector = encode_finding(original)
summary = decode_vector(vector)
# Preserve original: summary contains fh, not the original file reference or d.
```

`decode_vector()` returns `s`, `t`, `fh`, `l` and `a`. A truncated file-reference
hash cannot reconstruct the original path, and descriptions are not encoded.
Keep the original finding and evidence alongside vectors for complete human
reports. `AgentVectorBridge.decode_to_human()` returns structured dictionaries;
it does not generate French prose or call a language model.

The `tokens_saved_est` counter uses fixed per-operation assumptions, not provider
usage or a tokenizer measurement. No percentage reduction or decision-quality
gain is established by that counter. Measure encoded size and retrieval quality
on actual findings before integrating the prototype. The module's math routines
do not call an LLM; a host agent may use model tokens to interpret their output.
