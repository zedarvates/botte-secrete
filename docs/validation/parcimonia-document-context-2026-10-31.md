# Pinned document-content reading — 2026-10-31

## Source and behavior

Based on current main `4d1eb33a53151783758b4a6e475c3a0e0f9e5314`.
The full source snapshot and Git tree/commit identity were verified before work.
PR 157 had already merged; all 13 published checks succeeded at its original
head `83f5fd2368dda35c163e97ef94f5baf036ebc68c`. No merge was performed here.

`botte verify document-context` reads selected local Markdown/text through a
closed URI/version/path/raw-SHA-256 catalog. It rejects unsafe or ambiguous
catalog entries, verifies bytes before excerpting, and returns a lexical matching
line with raw-file/excerpt digests and character-column citations. It reuses the
existing evidence-path validator and recall snapshot contracts.

`--recall` consumes plain or inventory-linked receipts; `--references` accepts
explicit documentary identities. The recall path keeps upstream status/coverage,
reported outcome counts, declared comparison findings and an input digest.
Read uncertainty and existing contradictions cannot become completed context.
Context remains untrusted, non-executable data. No model, index, memory write or
automatic route is added.

## Executed evidence

| Check | Observed result |
| --- | --- |
| Canonical runner | 1779 passed, 0 failed; all 93 suites selected |
| New local-file and actual CLI contracts | 19 passed |
| Installed wheel outside checkout | 16 behavioral checks passed; installed import isolation separately asserted; pip check clean |
| Python 3.10 grammar | 4 changed/new Python files parsed; local runtime was Python 3.12 |
| Existing committed-rules audit | 100/100; 3 rules, 0 errors/warnings/conflicts/stale |
| Project checkup | Directives 100/100; expected absent project-local MCP declaration; global/plugin reachability not inferred |
| Local documentation links | No broken link reported; scanner explicitly incomplete on 6 pre-existing unsupported Markdown constructs |

The optional external cloud-source qualification remains skipped when its
separate checkout is not supplied. Skipped adapter qualifications are not counted
as workbench passes. No independent sub-agent review was performed for this
increment; authored tests and installed checks are the executed evidence.

Cases cover CRLF byte pins and line citations, long-line windows, Unicode ASCII
wire budgets, file/total/document limits, absent files, stale catalog/reference
pins, malformed paths/catalogs, symlinks, directories, a real nonblocking FIFO,
invalid UTF-8/binary sources, detected writes during reading, original failure
retention and plain/linked/unavailable recall. Installed checks read a real public
repository document and actual SQLite receipts, alongside labeled authored data.

## Artifact identity and limits

Reader SHA-256:
`43fea6c9688845e6d12d1c9c9e5c0074e229ee5de9f6d926fb8b77647fc0544c`.

Wheel SHA-256:
`ad73966f924c3305da56f43d73b012dd5a0c44b4b5a67a2891a6112d612d8692`.

Packaged-input manifest SHA-256:
`62af878ed6e0fc34a9653f1c8bad59f3978d3548cdda5267f324b5a3c1c7d2db`.
All 666 actual `skills/*` wheel inputs matched final source. The previously
qualified isolated declared-dependency environment was reused; the final wheel
was reinstalled and invoked outside checkout without PYTHONPATH/HOME overrides.
This was not another fresh-environment installation.

The reader selects at most one line-window per document. Hash agreement is
agreement with caller pins, not document truth, authenticity or freshness.
Consistency/path checks do not isolate a hostile filesystem owner. OS access
timestamps may change on reads. No real private-vault/model runtime, full wiki
coverage, semantic retrieval quality, tokens, latency or savings is qualified.
See the [content guide](../parcimonia-document-context.md).
