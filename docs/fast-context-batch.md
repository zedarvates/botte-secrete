# Prepare several source contexts for a local mission

`botte code batch` prepares a bounded set of explicit Zig/GDScript function
contexts inside one caller-selected project root. It reuses the locator and
checked-context workflow. No recursive discovery, index, model call, command
execution or file mutation is introduced.

```bash
botte code batch request.json --root /path/to/project --max-context-bytes 32768
```

A request file is at most 64 KiB, UTF-8 JSON, with unique keys:

```json
{
  "schema": "botte.code-context-request/v1",
  "items": [
    {"id": "client-spawn", "file": "client.gd", "name": "spawn_player"},
    {"id": "server-spawn", "file": "server.zig", "name": "spawn_player", "before": 2, "after": 40}
  ]
}
```

These are illustrative filenames/functions. Use the actual explicit sources for
the mission. Paths are relative to `--root`, independently of where request.json
lives. Review the request before using it: a request is data, not authorization.

## Request and scope

Requests contain 1–16 items, each with a unique `id`, `file` and exact ASCII
function `name`. Optional fields are `expected_sha256`, `occurrence`, `before`
and `after`, following the existing [single-source contracts](fast-context-symbols.md).
If expected_sha256 is present it must be a non-null lowercase SHA-256. Omitting
it selects labeled fresh discovery; a supplied stale reference is never replaced.
Unknown fields and malformed items are rejected before source files are opened.

Source paths must be relative POSIX `.gd`/`.zig` paths, at most 512 UTF-8 bytes.
Absolute/drive paths, backslashes, parent traversal and control characters are
refused. Source symlinks in the selected path are refused and resolved containment
is checked. This limits ordinary path traversal; checks are not an OS sandbox
or race-proof file-descriptor walk. Root/path authorization and later changes
remain the caller's responsibility. Each source read retains the 1-MiB cap;
fresh discovery can read each item twice.

## Shared budget and partial results

The shared raw-context budget defaults to 32768 bytes (256–131072). Item order
is caller order, not a semantic priority prediction. Each item gets at most
65536 remaining bytes. If fewer than 256 remain, later items are marked
`budget_exhausted` without opening their source files. Whole-line omission and
anchor-too-large rules remain visible; the declaration is retained before
surrounding context when it fits.

`botte.code-context-batch/v1` retains one row per request ID. Read failures,
missing functions, stale sources, ambiguity, over-budget declarations, omitted
windows and skipped items cannot become a completed batch. Successful earlier
contexts remain available with their hashes. A later successful read of the same
path with a different digest becomes `source_changed_between_items`; its text
is excluded so the batch does not silently mix those revisions. This check does
not recognize hard-link aliases or establish consistency across distinct files.

Exit 0 means every requested window completed without budget omissions. Exit 6
means an incomplete batch with per-item details. Exit 2 means invalid input,
request/root errors, or scope rejection, with JSON error on stderr. Source read
errors are retained per item and do not hide later valid items.

`context_bytes` counts included raw UTF-8 text, including repeated overlapping
windows. It is not total JSON size, tokens, billed usage or a memory limit.
The report sets `atomic_project_snapshot: false`: each window binds its own
read bytes, not an atomic client/server or Git checkout snapshot. `completed`
means requested windows collected; it does not mean complete function bodies,
valid code, compatible protocols, a successful task or permission to execute.

Python callers use `skills.fast_context.batch.prepare_code_batch(request, root)`.
The worker still needs project guidance, body/dependency review and its existing
mission/evidence contract. No actual LLM, wiki, Godot, Zig server or Odin worker
connection is qualified. No model or worker is activated by this command.

Validation: `python -m skills.fast_context.test_batch` plus the existing
FastContext, locator and workflow suites in the canonical runner.
