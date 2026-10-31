# Root-scoped code context batch — 31 October 2026

Base: draft #159 at `51b3673a88de01beb230048f630e7da9889d20a1`, tree
`42d331a71aba297510e0a8071dcfde18b7a7f9f5`. All three observed workflows
succeeded at that base. This is a separate candidate; no prior PR is merged.

## Behavior

`botte code batch REQUEST.json --root PROJECT` reads a caller-selected bounded
request, validates its entire explicit list before opening source files, and
reuses the single-source workflow in caller order. Source paths are relative to
the separately selected root; symlinks/traversal/absolute paths are refused.
A shared raw-text budget controls included windows. Every ID retains a result;
stale, ambiguous, missing, failed, over-budget and skipped entries remain visible.

Completed batches require all requested windows with no budget omissions. A
later successful read of the same path with a different digest is flagged and
its text excluded. The report is explicitly not an atomic project snapshot.

## Validation

- Canonical changed runner: 429 passed, 0 failed across all eleven selected
  suites. Scoped run, not a complete repository run.
- New batch suite: 13 tests passed, overlapping the canonical count.
- Mixed Zig/GDScript contexts preserve their exact bytes/digests. Shared-budget
  exhaustion stops later source opens; oversized anchors consume no text budget.
  Good entries remain available alongside stale, missing or unreadable ones.
- Whole-list validation before reads, unique IDs, root/path refusal, source
  parent/leaf symlinks, malformed/duplicate/nonfinite/oversized JSON requests,
  a nonblocking FIFO refusal, ambiguity and same-path revision changes tested.
  Symlink/FIFO checks depend on host support; no Windows qualification is inferred.
- Actual subprocess tests exercised completed exit 0, incomplete exit 6 and
  invalid-request exit 2. No requested source code was executed.
- Final wheel installed outside checkout: all 13 tests passed again. Isolated
  batch.py/cli.py imports match source hashes. The actual installed `botte`
  console script returned a two-source batch preserving authored GDScript CRLF
  and Zig source bytes exactly.
- Four files parse Python 3.10 grammar under Python 3.12.14. This is not execution
  on Python 3.10. Documentation and staged checks passed. Checkup completed with
  project-local MCP wiring absent.

## Limits

Fixtures are authored, not live game/client/LLM validation. Raw-context budgets
exclude serialized JSON, provider tokens and billing. Repeated/overlapping
windows are counted again. There is no deadline, recursive search, semantic
ranking, body parser, task completion decision or automatic execution route.

Ordinary path/symlink checks are not a race-proof descriptor walk or OS sandbox.
Hashes bind individual read snapshots, not all files together or a Git commit.
Different path aliases/hard links are not cross-correlated. A same-path change
keeps earlier windows with their hashes and marks the batch incomplete; this
is not an automatic retry or current-state lock. Read project guidance and
relevant dependencies separately. No secrets are detected/redacted automatically.

No token/cost/latency/quality saving, live wiki/LLM/Godot/Odin connection, merge,
release, deployment or worker/model activation is claimed.
