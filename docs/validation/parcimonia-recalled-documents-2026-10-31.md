# Recalled documentary-reference review — 2026-10-31

## Revision and scope

Based on draft PR 156 at `700e633afaf2bdc3f66011770ab9e1648332c995`.
All 13 published checks succeeded at that exact head, including Python
3.10/3.11/3.12, README smoke, reproduction and CodeQL checks. The PR remained
draft and unmerged.

That follow-up fixes a README smoke deadline: the earlier Python 3.10 job had
passed all 76 suites (1409 passed, 0 failed), then reported a generic checkup
error after about 31 seconds. A 30-second timeout is the likely explanation,
not a confirmed exception type: the old handler erased that information.
Checkup alone now has a bounded 120-second allowance; other commands retain
30 seconds. Four new runner contracts join the canonical selection, now
77 suites. Timeout and launch failures are explicitly distinguished.

The current increment adds optional `recall --inventory FILE`. It preserves
the original recall v1 contract without that option and uses a separate
`parcimonia.verification-memory-linked-retrieval/v1` envelope when supplied.
Exact URI/version documentary matches, version/kind mismatches, missing,
unknown and ambiguous references remain separate. Existing current-source
contradictions stay findings even if the supplied inventory matches an archived
reference. Report/source and documentary digest bases remain distinct.

The original inventory graph is reviewed separately with the existing helper.
No receipt edges or inferred relations are materialized. Caller declarations
do not establish truth, authenticity, document contents or current freshness.
This is supplied-snapshot review, not a live wiki or model connection.

## Executed checks

| Check | Observed result |
| --- | --- |
| Canonical runner | 1438 passed, 0 failed; all 77 suites selected |
| Helper and actual CLI/SQLite integration | 30 passed: 20 helper cases and 10 CLI cases |
| Existing quarantine Gauntlet | 11 passed, 0 failed |
| Installed wheel outside checkout | 29 behavioral checks passed, plus a separate import-isolation check |
| Independent final review | 18 targeted checks passed, 0 failures; no remaining blocker in scope |
| Python 3.10 grammar | All 8 changed/new Python files across this feature and preceding deadline fix parsed |
| Documentation and staged checks | Local-link, whitespace, secret, JSON and Python-syntax checks passed |

The optional external cloud-source qualification was explicitly skipped because
that separate checkout was not supplied. Skipped adapter qualifications are
excluded from the workbench pass count. The new helper does not change the
SQLite reader, conformance implementation or deployed cloud service.

Meaningful cases include real checkpointed Memory Hub data; retained failures
and citations; exact matches; complete-inventory absence versus partial-inventory
unknowns; duplicate node identities; wrong kinds; existing dependency cycles;
source-declaration contradictions; unavailable/incomplete input; unchanged input
objects and database files; malformed snapshots; and escaped Unicode under the
final 8192-byte JSON cap. Review found copied graph details could overflow that
ASCII cap: explicit trimming and omission counters corrected it before final
qualification. Omissions never become a completed review.

## Package and reader identity

Final helper SHA-256:
`461525c8ac47aa0b970d387fbf7b065cfe903389590692e3ad4f97c67c8043a4`.

Wheel SHA-256:
`f46ae24600c44a62374326a795f57f6bf9e14a218a0303e4455a7e379060edcd`.

Packaged-input manifest SHA-256:
`4964650d1d999047f868eb50a5c60b7adc336a3556235a7548f43f498c8091fe`.

All 628 actual `skills/*` wheel inputs matched final source. The previously
qualified isolated environment and declared dependencies were reused; the final
wheel was reinstalled and `pip check` was clean. Commands ran outside checkout,
with installed imports and without `PYTHONPATH` or `HOME` overrides. This was
not a second fresh-environment qualification.

No merge, corpus import, routing activation or deployment occurred. No token,
cost, latency, semantic-retrieval-quality or game-performance gain is established.
See the [recall guide](../parcimonia-memory-recall.md).
