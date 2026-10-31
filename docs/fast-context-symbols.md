# Locate a Zig or GDScript function

The local FastContext CLI can locate an exact function name in one explicitly
selected `.zig` or `.gd` file:

```bash
python -m skills.fast_context.cli symbol server.zig spawn_player
python -m skills.fast_context.cli symbol client.gd spawn_player --max-results 5
```

The compact `botte.code-symbol-locations/v1` JSON reports candidate declaration
lines, character columns, snippets and SHA-256 of the exact UTF-8 source bytes.
An empty result means the bounded read completed without matching this lexical
pattern. Read/encoding/argument failures use exit 2 with a JSON error on stderr;
successful reads, including empty results, use exit 0.

Python callers can use `skills.fast_context.symbols.locate_symbol` for supplied
text or `locate_symbol_file` for the same explicit-file behavior as the CLI.
No directory is scanned, code executed, index stored or model contacted. Existing
`explore` and cache behavior remain unchanged; this command does not use the cache.

## What the locator recognizes

- Zig `fn name(` declarations, including common `pub`, `export`, `extern`,
  `inline` and `noinline` modifiers.
- GDScript `func name(` and `static func name(`, including indented declarations.
- Exact case-sensitive ASCII identifiers, up to 128 characters.
- Line comments and ordinary quoted text are masked; GDScript triple-quoted
  text and Zig multiline-string lines are excluded from candidate declarations.

This is a lexical locator, not a parser or compiler. A declaration prefix must
be on one physical LF/CRLF line. Zig quoted identifiers and cross-line declaration
prefixes are unsupported. Malformed source is not validated; ambiguous lexical
constructs can still cause false positives or omissions. The report explicitly
sets `syntax_checked: false` and `body_included: false`.

## Bounds and provenance

One NUL-free UTF-8 file of at most 1 MiB is read. The result limit is 1–20 and
each snippet is at most 1024 UTF-8 bytes. Truncation and omitted candidate counts
are explicit. SHA-256 changes when the bytes change, including line endings;
reconcile it before relying on an old line reference. It authenticates neither
the author nor a Git commit, and it is not an execution lock.

The local file reader refuses non-regular files and leaf symlinks, using
nonblocking/no-follow flags where available. It is not an OS sandbox or a
repository allowlist; parent path selection and access authorization remain the
caller/host's responsibility. No secret detection or redaction is implied.

A worker can use the result to choose a subsequent bounded source read. It must
still read the function body, dependencies and project guidance before editing.
This prepares a source lookup capability; no live LLM, wiki, Godot, server or
Odin worker connection is qualified by these checks.

Tests: `python -m skills.fast_context.test_symbols` and
`python -m skills.fast_context.test_fast_context`. Both run in the canonical
repository runner. GG Framework's symbol-first retrieval motivated the scoped
locator; no upstream code was copied.
