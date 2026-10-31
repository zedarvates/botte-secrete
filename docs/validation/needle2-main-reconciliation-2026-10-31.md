# Needle 2 — reconciliation with main, 2026-10-31

Base: `4cec74fb12c918bcac6967ce84054e5dafda80b9`.
Preserved PR head / historical reproduction source:
`02be6033c7a73788643ee5e7cf6ad6e071394e02`.

## Acceptance scope

Integrate the advisory software while preserving the failed model study as
historical evidence. No model, native Needle library, remote memory service,
worker deployment or routing activation is qualified by this reconciliation.
The reserved model-validation split remains unexecuted.

The source merge had two conflicts, in CI and README command checks. Resolution
retains current main's exact-source checks, runtime matrix, dependencies,
registered rules, memory regressions and 120-second checkup smoke timeout.
New advisory/harness tests are registered in the canonical runner. A separate CI
job checks out the immutable historical SHA above and reproduces its evidence.

## Reproduced defects and corrections

- `memory_pilot.propose()` could expose `executable: true` with the existing
  lexical router, despite its advisory envelope. Every adapter's route is now
  explicitly non-executable. Spies reject attempted memory/MCP dispatch.
- The argument-span CLI could wait on a FIFO despite its byte limit. It now
  refuses detected leaf symlinks and non-regular descriptors, opens nonblocking
  where supported, and reads at most 8,193 bytes. Its archived example retains
  its old binder digest; new outputs report their actual binder digest.
- The harness retained aliases to nested requested/executed states. Recorded
  deltas are deep-copied and revalidated before handoff.
- The checkpoint adapter could export a cached handoff after uncertainties
  changed. It now rebuilds from current state while preserving explicit progress.
- The Atlas seed accepted fabricated comparison data as historical measurements.
  It now requires the exact comparison and protocol digests, bounded regular-file
  input, finite measurements and consistent denominators.

## Historical versus current evidence

The historical study protocol, model reports, corpus bytes, selection and
diagnostic archive are unchanged. Historical source/test/document attachments
are not silently rebound to current code. The integrated source intentionally
fails the historical source checks and diagnostics refuse stale attachments
before runtime/classification or result creation.

The current study contract tests use two separately authored 20-case temporary
fixture sets and temporary source snapshots. These fixtures establish software
contracts only. Archived-row scoring is checked separately as data consistency,
with current source drift kept explicit; it does not qualify new inference.

## Observed verification

- Canonical local runner: **2,466 passed, 0 failed; all 128 suites**.
- Includes **149 routing/argument/study checks**, zero skips, and **52 harness
  checks**. These counts overlap the full total and are not additive unique cases.
- Historical source export at the exact SHA: **18 original archive/diagnostic
  tests passed** without a model, network service or corpus rewrite.
- Existing shared-memory service/transport/recovery pytest matrix: **127 passed**.
  These checks overlap other memory suites and are reported separately.
- README commands: **11 passed, 0 failed, 12 intentional skips**.
- All **703 tracked Python files** accepted Python 3.10 grammar under local
  Python 3.12; this is not a local Python 3.10 runtime claim.
- Checkup completed: no high-severity taint candidate; missing project-local MCP
  declaration remains environment drift. Runtime reachability was not checked.
- Documentation checking remains explicitly partial for existing multiline,
  blockquote and HTML constructs; it is not a complete local-link proof.
- Separate reviewers examined routing/authority, historical test separation and
  harness state/provenance boundaries. This is not third-party certification.

Hosted checks must qualify the final candidate before merge. The source-exact
historical CI job must pass independently of the integrated runtime matrix.

## Six acceptance axes and limits

Selection retains the read-only five-tool catalog and existing memory schemas;
host project/identity authority is unchanged. Consequences are proposals and
explicit result files, not memory writes. Pipeline acceptance requires both
historical integrity and current software checks. Existing-output refusals and
partial journals retain interruption evidence; no automatic inference replay is
added. Experience stays tied to its source/version and failed selection.

There is no measured model-quality, latency, token or monetary gain from this
integration. The decision remains `stop_insufficient_safe_coverage`, with no
selected threshold or successful-action-ledger eligibility. New model evaluation
requires a distinct frozen protocol and suitable independent task evidence.
Filesystem guards are not OS isolation or complete I/O deadlines. The harness
contains caller-declared evidence and rights metadata, not external attestation
or legal clearance.
