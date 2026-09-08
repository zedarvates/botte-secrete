---
name: prefix_tree
description: Store named prompt prefixes and compare later text with their baseline. Use for inspecting common prefixes or evaluating a baseline-aware prompt transport; this module does not send or reconstruct messages.
---
# prefix tree

Stores complete prefix strings in a mapping keyed by agent name. Despite its
name, this implementation is not a compressed trie or a transport protocol.

## Usage

```bash
python -m skills.prefix_tree.cli --help
python -m skills.prefix_tree.cli register fixture --prefix "sample baseline"
python -m skills.prefix_tree.cli diff fixture "sample baseline plus context"
```

## Consequences and verification

Read [effects.json](effects.json). `register` replaces an entry and rewrites
`~/.botte/prefix-tree-store.json`. This user-wide JSON stores **complete prompt
text without encryption**. CLI arguments can also remain in shell history or
process inspection. Use task-appropriate data and output recipients.

`diff`, `common` and `stats` read state; `diff` does not update the stored baseline.
An unknown or empty baseline returns the full input. For a non-empty baseline,
exact equality returns `[no change]`. An append returns `[diff:+Nc] ` followed
by the exact suffix, including whitespace. Shortened or otherwise changed text
returns the full replacement, including an empty string for deletion. CLI
printing adds its usual terminal newline.

These strings have no unambiguous message type, baseline digest or receiver
acknowledgment. Do not use them as a lossless wire protocol without adapting
the transport. A downstream model cannot reconstruct omitted text unless the
receiver actually has the same baseline. Re-register only after deciding which
baseline the target workflow should use.

Writes have no lock or automatic rollback; a concurrent writer can overwrite
another update. Preserve prior state before replacing useful prefixes, and
inspect actual state after failure before retrying. A read retry can disclose
the same output again. The stats savings field is a heuristic, not measured
token usage or evidence of transport savings.

For plausible reuse, define typed full/append/unchanged messages with a baseline
identity and test exact reconstruction, deletion, whitespace, stale receivers
and marker-like input in the target harness. Keep this an adaptation to test;
record evidence and context before promoting it. See the
[common contract](../../docs/capability-effects.md).
