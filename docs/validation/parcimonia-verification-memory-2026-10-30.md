# Verification memory and documentary-link qualification

Date: 2026-10-30. Candidate 1.11.0, based on draft PR 154 head
`8faf4989cde3214caf0be24b63e981ae5b02957d`. That head had eight observed
successful GitHub checks when re-read; its PR remained open, draft and unmerged.
This increment connects local receipts to existing Memory Hub quarantine and
adds pure documentary-link review. No store schema or lifecycle was changed.

## Executed evidence

- Canonical `scripts/run_tests.py --prioritize -q`, with the external cloud
  source checkout explicitly supplied: **1380 passed, 0 failed, 76 suites**.
  Every selected suite was retained. Without that checkout the one external
  conformance qualification is skipped explicitly, not counted as a pass.
- Targeted bridge/link/CLI: **36 tests passed** (13 bridge, 19 links, 4 CLI).
  Raw-reader tests and two additional MCP contracts also pass.
  The existing `python -m skills.memory_hub.test_quarantine` Gauntlet separately
  completed with **11 passed, 0 failed**.
- The fresh SQLite roundtrip used the six individual reports from the prior
  authored demonstration: **10 assertions passed**, six observations stored,
  repeated persistence made no updates, normal context remained empty and
  explicit quarantine review retained non-executable labeling. Exact declared
  document links resolved; injected missing/stale cases were detected separately.
- **42 fresh installed-runtime checks passed** on Linux/Python 3.12 with declared
  dependencies and a clean `pip check`. Installed CLI commands ran outside the
  checkout without injecting `PYTHONPATH` or overriding HOME. MCP discovery and
  call succeeded; read-only annotations were checked with the full catalogue
  because lazy search currently returns schema without annotations.
- README commands: 11 passed, 0 failed, 10 intentional skips. All changed/new
  Python files (14) parse with Python 3.10 grammar; 79 Markdown files have no
  broken local links.
  Project checkup completed with the source-checkout MCP declaration still
  absent and runtime/reachability not checked, rather than inferred available.

Wheel SHA-256:
`78422bfaa2cb17562661d1389794052f981f714e92ad9d5c269df652a0a5eee7`.
Packaged-source manifest SHA-256:
`662fc1f910475fd0f1c951e37feb50ae0d95faced14a2c933de35bc87930f03e`.
All 646 packaged inputs remained unchanged during qualification and the final
source comparison.

## Independent review corrections

The bridge preserves context-mismatch failure observations and omits raw
baseline/output/boundary payload sentinels. Lookup plus persistence is atomic:
two competing SQLite connections produced stored/already_present, exactly one
row at version 1 and access count 0. Existing entries with altered lifecycle,
source or protected metadata return conflict without overwriting. Caller
transactions are refused; role and execution flags are forced by the adapter.

Knowledge-link review rejects malformed enums, labels lexical/detail omissions,
and keeps normalized-inventory digest basis explicit. Output-budget boundary
corrections and independent graph-resolution probes passed. Only supplied,
resolved-current depends_on edges enter dependency-cycle checks.

## Scope

Sources, versions, confidence, completeness and documentary relationships remain
caller declarations. Report digests identify bytes, not truth, freshness or
external authenticity. Pure link review dereferences no URI. Memory preview
writes nothing; explicit persistence goes only to private non-executable
quarantine and does not enter normal context. Promotion remains blocked by
existing Memory Hub behavior. The separate Parcimonia episode format has not
been adapted here.

No live wiki/index, private corpus, LM Studio backend, GUI/game control, model
training, cloud deployment or measured end-to-end cost/speed gain is qualified.
See the [workflow guide](../parcimonia-verification-memory.md) and
[knowledge inventory](../parcimonia-knowledge-inventory.md).
