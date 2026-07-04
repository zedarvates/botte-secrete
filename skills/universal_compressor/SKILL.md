---
name: universal-compressor
description: "Headroom-inspired multi-type compression — text, JSON, logs, tool output, code. Reversible. MCP server compatible."
version: 1.0.0
---

# Universal Compressor

Headroom-inspired multi-type compression for botte-secrete. Reduces token usage by 40-90% depending on content type. Works as library, CLI, or MCP server.

## Strategies

| Content Type | Strategy | Typical Savings |
|---|---|---|
| `text` | Dedup lines, collapse blanks | 0-30% |
| `json` | Compact + truncate large arrays | 20-60% |
| `log` | Pattern dedup + sampling | 80-98% |
| `tool_output` | Head+tail, strip ANSI | 50-90% |
| `code` | Strip comments, collapse imports | 20-40% |
| `auto` | Auto-detect content type | Best effort |

## Usage

```python
from skills.universal_compressor import compress, restore

# Compress with auto-detection
result = compress(content)
print(f"{result.original_size} → {result.compressed_size} ({result.ratio:.0%})")

# Compress with type hint + reversibility
result = compress(big_log, content_type="log", reversible=True)

# Restore original
original = restore(result.reversible_key)
```
