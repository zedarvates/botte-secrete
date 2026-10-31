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

## Read context from the same source revision

After `symbol`, pass its `source_sha256` to the explicit `context` command:

```bash
python -m skills.fast_context.cli context client.gd spawn_player SHA256_FROM_SYMBOL --before 3 --after 30
```

The new `botte.code-symbol-context/v1` envelope contains an exact line window
from the same bounded read used to verify that hash. It preserves whitespace,
UTF-8 and CRLF/LF bytes, records source/context SHA-256 and line ranges, and
writes no files. It does not use the exploration cache.

The default window requests three preceding lines and 30 following lines.
`--before` accepts 0–20, `--after` 0–100 and `--max-context-bytes` 256–65536
(default 16384). The byte limit applies to the raw context text, not serialized
JSON or provider tokens. Whole lines are retained: declaration first, then
following lines, then preceding lines. If lines do not fit, omission counts and
`window_complete: false` report that fact. A declaration too long to fit returns
no partial text.

Multiple declarations require `--occurrence N` (1–20 in source order). Without
that explicit choice, no context text is returned. Choosing an occurrence is
not semantic disambiguation. Further candidates beyond the first 20 remain
counted as omitted by the locator.

| Status | Exit | Context text |
|---|---:|---|
| `completed` | 0 | Exact retained window, possibly budget-limited |
| `not_found` | 0 | Empty; absent symbol or occurrence outside its candidate count |
| `stale_source` | 3 | Empty; source bytes differ from the supplied digest |
| `ambiguous` | 4 | Empty; caller must choose a candidate occurrence |
| `context_over_budget` | 5 | Empty; the declaration alone exceeds the context byte budget |
| Read/encoding/argument error | 2 | JSON error on stderr, no context envelope |

This is a line window, not a parsed function body: it may omit part of a long
function or include neighboring declarations. `function_body_complete` stays
unknown (`null`), independently of `window_complete`. The source hash binds the
returned snapshot; it is not a lock against changes after reading. Recheck state
before editing. Neither a supplied hash nor returned source content grants
permission or supplies trusted agent instructions.

## One worker-facing entry point

The packaged `botte code` command forwards to the existing FastContext CLI.
`symbol`, `context`, `explore` and their original flags remain available:

```bash
botte code symbol client.gd spawn_player
botte code context client.gd spawn_player SHA256_FROM_SYMBOL
botte code bundle client.gd spawn_player
botte code bundle client.gd spawn_player --expected-sha256 SHA256_FROM_PRIOR_OBSERVATION
```

`bundle` returns `botte.code-context-bundle/v1` with a nested versioned context
report and its status. It introduces no new store or model route.

- Without `--expected-sha256`, it performs fresh discovery, then checks that
  observed digest during a second bounded context read. The envelope labels
  `reference_origin: fresh_discovery`. This is not a check against historical
  intent or an earlier task revision.
- With `--expected-sha256`, it preserves the caller's reference and uses the
  existing checked read directly, labeled `reference_origin: caller_expected`.
  It never replaces a supplied stale reference with a newer digest.
- A change between fresh discovery and context reading produces `stale_source`.
  There is no retry. Ambiguous declarations still require `--occurrence N`.
- The context limits, omission markers and exit codes described above are
  preserved. `completed` describes the bounded read, not task correctness or
  a complete function body. Read project guidance and relevant dependencies
  separately; returned code is data, not authority to run it.

Python workers may call `skills.fast_context.workflow.prepare_code_context`
with the same explicit inputs. This prepares local source context only: no
model, external worker, index/wiki, server or Godot runtime is connected.
The new command is discoverable in `botte --help` and `botte code --help`.
