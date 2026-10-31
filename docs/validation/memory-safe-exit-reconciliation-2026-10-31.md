# Memory quarantine and SAFE-EXIT reconciliation — 2026-10-31

## Candidate scope

Base: `35b3ce47f672d4ba35aac16177a5ac1f96de0ad6`.
Preserved source heads: PR #92 `41c2054e3b08b5db060f5e47d533023737397586`
and PR #93 `724f56d2636ea2959befe00f62c14a14529a3278`.
Both histories merge into the base without textual conflicts. New changes below
were required by boundary checks; an automatic textual merge alone was insufficient.

## Observed defects and corrections

- With `max_tool_calls=0` and `max_wall_seconds=0.05`, the initial harness executed
  a 0.2-second child and reported it passed after approximately 0.224 seconds.
  The updated harness checks before dispatch, stops at the exact call limit,
  and gives the direct child a timeout bounded by the remaining monotonic budget.
- An initial guard stopped for no progress and then returned `CONTINUE` after
  an improved score. `UNCERTAIN` is now terminal for that guard.
- Reusing an uncertain harness reset its guard and executed a completed step
  again in the same session. Reusing either the session or consumed plan now
  raises before dispatch. A supervisor must create a new explicit run.
- The CLI returned exit 0 for an uncertain run containing passed/skipped steps
  and no failed step. Such runs now return exit 2.
- Nonfinite budgets/scores/clocks and invalid authorization tiers are rejected.
  Snapshot presence is a syntactic identifier check; its recoverability is the
  caller's responsibility. No new execution authority is granted by this gate.

## Repeatable tests and transport boundary

All new tests use the standard library and are registered in the canonical full
runner, including quarantine and direct-child integration cases. The targeted
unit/integration run reports **42 passed**, including a real timed child,
zero/exact-call budgets, persisted stop state and no-replay checks.
A separate agent reviewed the raw code/diff and reproduced the replay and CLI
failures before checking their corrections. This is an additional code review,
not independent third-party certification or production evidence.

During full validation, automatic approval review rejected continuation of the
old ingestion test because its private-host HTTP payload was not established.
Source inspection confirmed an automatic probe of a hard-coded private Qdrant,
conditional writes and collection deletion. The existing hermetic test from
`2d77b5d2e93d9cd0e1c68f719dc3ac822abecbb2` is reused here, with a stricter
transport fixture: only the exact temporary loopback page is fetched using an
opener with environment proxies disabled, Qdrant is
an in-memory contract double, embedding failure is mocked, backend discovery is
mocked, and model reflection is disabled. **14 ingestion checks pass**. These do
not qualify an actual Qdrant or embedding service.

## Validation and limitations

- Full runner: **1,729 passed, 0 failed, 91 suites**. This run preceded the final
  proxy-disabling adjustment to the test fixture; its 14 checks passed again
  after that adjustment. Hosted CI must qualify the final published tree.
- README command checks: **11 passed, 0 failed, 10 intentionally skipped**.
- Checkup completed: no high-severity taint candidate; missing project-local MCP
  declaration is retained as environment drift. Runtime reachability was not tested.
- Documentation link checking reports incomplete coverage of six pre-existing
  multiline/blockquote constructs; that result is not a complete link proof.
- Tests run locally on Python 3.12; hosted Python 3.10/3.11/3.12 checks must pass on
  the published candidate before merge.

Quarantine applies to the explicit `store_external` path. Existing external
callers are not automatically migrated, and trusted local stores remain available.
Memory text does not acquire executable authority through promotion. Timeout
coverage is for the direct subprocess; no OS isolation, process-tree cancellation,
remote deployment or live model/homelab qualification is claimed. A crash during
an action still requires supervisor reconciliation; no automatic replay is added.
