---
name: token_compressor
description: Encode UTF-8 text with the reversible TC1 zlib/base85 codec and decode it with TokenCompressor.expand. All accepted level names use this same codec. Use for encoded transport with a compatible decoder, not direct model-readable context compaction or a promise of fewer model tokens.
---

# Token Compressor — reversible text codec

`TokenCompressor.compress()` compresses UTF-8 bytes with zlib and base85-encodes
them under a `TC1:` prefix. `expand()` restores that self-contained payload.
All current levels (`auto`, `hash`, `pair`, `json`) select the same codec;
historical semantic hashing, pruning and schema transforms are not called by
`compress()`.

```python
from skills.token_compressor.cli import TokenCompressor

codec = TokenCompressor()
original = "Keep every value, including whitespace and Unicode."
encoded = codec.compress(original)
assert codec.expand(encoded) == original
```

The result requires a compatible decoder. It is not a compact prompt a model can
read directly, and fewer encoded bytes do not prove fewer model tokens. Encoding
overhead can increase the size of small inputs. Verify the round-trip and measure
size on representative content before choosing this transport.

```bash
python -m skills.token_compressor.cli --help
python -m skills.token_compressor.cli compress --help
```

The CLI prints measurement lines as well as the TC1 payload. Do not pass its
entire stdout to `expand()` as though it contained only encoded data. The `learn`
subcommand writes n-gram frequencies under `~/.botte/ngram-freq.json`; those
frequencies are not used by the current `compress()` codec. Compression and
expansion do not call an LLM, while a host agent may consume model tokens when
using or discussing their results.
