---
name: prefix-pruner
description: Prune recognized context sections using stored retention/skip counters. Use to evaluate context reduction on a copy after checking which instructions and information the task requires.
---
# Prefix Pruner

Selects recognized sections using local history. Counters record this pruner's
keep/skip decisions, not observations that an agent read or needed a section.

## Strategies

| Strategy | Retention rule |
|---|---|
| `auto` | Keep score >= 0.3 or use_count == 0. |
| `aggressive` | Keep score >= 0.3; new sections start at 0.5. |
| `conservative` | Keep use_count > 0 or skip_count == 0. |

## Usage

```bash
python -m skills.prefix_pruner.cli prune < context.txt
python -m skills.prefix_pruner.cli tree
python -m skills.prefix_pruner.cli stats
```

## Consequences and verification

Read [effects.json](effects.json). `prune` can repeatedly rewrite the shared
user-level `~/.botte/prefix-tree.json`, even when every section is kept. With zero
or one selected span it returns the input without registering sections. `tree`
and `stats` read stored metadata. `--output` replaces the selected output file;
keep the original context separately. Pruning diagnostics go to stderr.

Only rejected spans are removed; retained text, unmatched gaps and source order
are preserved. Overlapping matches use the earliest outer span once. Regex
matching is not a semantic parser and can include authoritative instructions.
Do not treat a score as permission to discard task requirements. Inspect the
actual diff before using the result as model context.

The store contains section hashes, types, estimated token counts and counters,
not full section text. These are user-wide rather than task-bound. There is no
concurrent-writer lock or transactional persistence, and repeated runs change
the counters. Inspect output and state before a retry; restore from a prior copy
if needed. Missing or malformed history does not establish irrelevance.

For reuse in another harness, validate representative tasks with and without
pruning, including instruction retention and task quality. Token counts use a
character heuristic; fixed savings percentages are not established. Record
observed differences and remaining uncertainty through the task's report.
See the [common contract](../../docs/capability-effects.md).
