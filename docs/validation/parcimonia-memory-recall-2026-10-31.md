# Verification-receipt recall qualification — 2026-10-31

## Candidate and behavior

Based on draft PR 155 at `4ed871d637cceb32d608cee120a3f92f29a9cad5`.
The restored source snapshot contained 964 files; every Git blob and the
original Git tree/commit identity were verified before development resumed.
PR 155's 13 published checks succeeded at that exact head. It remained draft
and unmerged at the review observation.

This increment adds `botte verify recall`: explicit-project lexical selection
from existing checkpointed Memory Hub verification quarantine, with source
versions, declared raw-report digests and documentary references. It sanitizes
the status/counter projection, keeps failures and selected context-drift counts,
and declares omitted detail. It does not search arbitrary issue prose or detailed
failure signatures. Source comparisons are against caller declarations; source
freshness and report authenticity stay unknown.

Missing, invalid, active, oversized or changing databases are unavailable;
bounded scans/results are incomplete. Empty results require an exhausted eligible
scope. Read-only immutable SQLite avoids migrations, access-counter writes and
WAL sidecar creation; a nonempty WAL/journal is refused. A 64 MiB file ceiling
precedes connection. Python 3.11+ also sets a 1 MiB SQLite value limit; Python
3.10 has the file ceiling and bounded projection guards. Cooperative time/work
limits are not an OS sandbox or protection from an adversarial filesystem owner.

## Executed verification

| Check | Observed result |
| --- | --- |
| Canonical `python scripts/run_tests.py -q` | 1410 passed, 0 failed, all 76 suites selected |
| New helper and real CLI/SQLite contracts | 30 passed: 25 helper cases and 5 command integrations |
| Existing quarantine Gauntlet | 11 passed, 0 failed; ordinary context and promotion boundary preserved |
| Fresh installed wheel outside checkout | 32 checks passed; declared dependencies installed; `pip check` clean |
| Independent final review | 17 checks passed, no remaining blocking finding in the documented scope |
| Python 3.10 grammar | All 5 changed/new Python files parsed |
| Documentation | Local links checked after documentation edits |
| Project checkup | Directives 100/100; expected missing project-local MCP declaration; global/plugin/runtime reachability not checked |

The optional external cloud-source conformance case was explicitly skipped
because that separate checkout was not supplied in this environment. Skipped
adapter qualifications are excluded from the workbench's pass count. This
increment does not change the conformance implementation or requalify deployment.

Actual SQLite and subprocess cases cover failures and report/document citations,
unknown and mismatched source declarations, private agent selection, exact
file/counter/version stability, malformed records, Unicode, row/input/result/output
budgets, missing stores, old schemas, active WALs, symlinks and oversized files.
Independent probes additionally committed a real concurrent writer to confirm
snapshot invalidation and exercised the actual SQLite VM-work limit. A review
found the conformance `mismatch` counter was omitted; it was corrected and
regression-tested before final qualification.

## Artifact identity and limits

Final `memory_retrieval.py` SHA-256:
`73f32c2b112087ad851251fb35ae99719cce4d8051c3888d75c4a1113df4c6a7`.

Installed wheel SHA-256:
`495933c6c21033d3a1ccd58c0d6e976e5ce7d7d8dcdfc537b1c2ba9b63c1578f`.

Packaged-input manifest SHA-256:
`08ae4b289b835f9be2a3267a7c95cee9c5eee6b23bd9047290673b045b21c0c2`.
All 626 actual `skills/*` wheel inputs matched the final checkout, including the
new reader. The fresh environment ran the installed CLI from outside the source
directory without `PYTHONPATH` or `HOME` overrides.

These are authored contract checks, not measurements of semantic retrieval
quality, real wiki synchronization, target software reliability, game latency,
provider usage or cost savings. No model route, public listing, merge or cloud
deployment was activated by this increment. See the
[recall guide](../parcimonia-memory-recall.md).
