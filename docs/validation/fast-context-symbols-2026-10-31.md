# FastContext Zig/GDScript locator — 31 October 2026

Base: draft #158 head `48b63cafde640a066bdf12aadcb47f2bf83d4274`
(tree `ff203b76681d771c7d3bd368370ac46e9500226e`). Its three observed
workflows succeeded; this does not qualify the new locator.

## Implemented behavior

The existing FastContext CLI gains an explicit-file `symbol` command. It locates
case-sensitive ASCII function declaration candidates in Zig and GDScript with
line/column references, truncated snippets, omitted-candidate counts and SHA-256
of the exact UTF-8 file bytes. It reads no more than one 1-MiB regular file and
refuses leaf symlinks/non-regular files. Existing explore/cache behavior is
unchanged. The new command writes no files and calls no model/backend.

## Validation

- Canonical changed runner: 394 passed, 0 failed across all nine selected suites.
  This is scoped; no complete repository run is claimed.
- New locator suite: 16 tests passed. Existing FastContext: 34 checks passed.
  These overlap the canonical count and must not be added to it.
- Masking, exact names, Zig modifiers, GDScript nested/static declarations,
  multiline quoted text/comments, escaped quotes, BOM/CRLF, Unicode byte bounds,
  result omissions, changed source digests and invalid input exercised.
- Local file tests included missing/oversized/invalid-UTF8/NUL sources,
  directories, a refused leaf symlink and a FIFO rejected without blocking.
- An actual CLI subprocess read an authored GDScript fixture of 8149 bytes and
  found `spawn_player` at physical line 301 with the exact SHA-256
  `9d1e9a072e398ef1f2c2f8b7becd910147919825ff137a54b5b2cc3e5cc176e0`.
  Reproduce source: 300 repetitions of `# authored fixture padding` plus LF,
  followed by `static func spawn_player(peer_id: int):` plus LF and
  `    pass` plus LF. Exit 0 and source digest verified in the calling process.
- Final wheel installed outside checkout under isolated imports: all 16 tests
  passed again; symbols.py, cli.py and test_symbols.py hashes match source.
- Four files parsed with Python 3.10 grammar under Python 3.12.14. This is not
  execution on Python 3.10 or Windows. FIFO/symlink checks depend on host support.
- Checkup completed with project-local MCP wiring absent. No live local-model,
  Godot, Zig server or Odin worker connection is inferred.

## Limits

This is a lexical declaration locator, not an AST parser, function-body
extractor, compiler or game test. Multiline declaration prefixes and Zig quoted
identifiers are unsupported. The caller must still read relevant bodies,
dependencies and project guidance. A source hash binds bytes, not authenticity,
Git state or current state at a later edit. Parent path authorization is the
caller's responsibility; the reader is not an OS sandbox or secret filter.

The fixture is authored, not an incident or our live game client. No cost,
provider-token, speed or model-quality gain is established by returning a small
location report instead of source content. No merge, release, deployment or
automatic worker/model activation is included.
