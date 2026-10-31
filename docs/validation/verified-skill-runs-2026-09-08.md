# Verified skill runs: initial validation

Validated on 2026-09-08 in an isolated Linux checkout, using Python 3.12.13.
The implementation builds on capability-effects commit
`647ac7ce37904b32a9252fefa7cddd275caf652c`. The follow-up branch is
`feat/verified-skill-runs-v1`, targeting `feat/capability-effects-v1`.

## Automated results

All 192 tests below passed after integrating the parent branch's runtime
observation changes. These are selected regression and integration suites,
not a claim that the repository's full test matrix was run.

| Command | Passed | Failed | Skipped |
|---|---:|---:|---:|
| `python -m skills.conductor.test_verified` | 20 | 0 | 0 |
| `python -m skills.conductor.test_verified_pilots` | 4 | 0 | 0 |
| `python -m skills.conductor.test_conductor` | 25 | 0 | 0 |
| `python -m skills.conductor.test_effects` | 16 | 0 | 0 |
| `python -m skills.conductor.test_observations` | 12 | 0 | 0 |
| `python -m skills.capabilities.test_effects` | 19 | 0 | 0 |
| `python -m skills.capabilities.test_effects_operations` | 4 | 0 | 0 |
| `python -m skills.prefix_pruner.test_prefix_effects` | 7 | 0 | 0 |
| `python -m skills.llm_mcp.test_lazy` | 34 | 0 | 0 |
| `python skills/test_e2e.py` | 51 | 0 | 0 |

Tests used `BOTTE_NN_AUTO_LABELS=0` to keep fixture traffic out of production
learning. The optional `jsonschema` 4.26.0 package was available through an
isolated development dependency directory, so schema validation was exercised
without skips. Both schemas were checked with `Draft202012Validator`, including
preview, unverified, verified, reused and stale execution reports. The runtime
itself uses the standard library for these contracts.

The two new suites are registered in `scripts/run_tests.py`. Python 3.10/3.11
and Windows were not executed in this validation. GitHub workflows currently
target PRs into `main`; a stacked PR into the capability-effects branch does
not automatically provide that CI matrix.

## Independent workflow exercise

A separate agent used the skill instructions to construct an isolated order
processing workflow without changing the implementation. The producer exited
zero but wrote incomplete JSON. Its consumer stayed blocked while an independent
checksum step completed. Resumption repeated no writes; a new recovery plan
produced three orders totaling 3600 cents.

The exercise exposed a defect: after a required CSV changed from a total of
3600 to 3700 cents, the original implementation reused the stale output. The
fix rechecks `requires` before reuse and dependency consumption. A narrow
independent retest then returned CLI exit 1, `complete:false`, and `stale` for
both dependent results. The command log still contained only the two initial
executions. Historical precondition evidence stayed intact; the separate resume
checks recorded the changed input hash. Both regression cases are now in
`test_verified.py`.

## Pilot coverage

| Pilot | Evidence exercised | Limit |
|---|---|---|
| Checkup | Actual checkup/advisor/registry code creates the inherited registry file and the audit artifact. | Hardware/backend discovery uses fixtures; the pilot blocks URL opening and does not validate a live fleet. |
| Conductor | Real child processes write artifacts; explicit dependencies block incomplete work; successful results are rechecked without duplicate writes. | Local cooperative checkpoints; no distributed lease, transaction or authenticated attestation. |
| Prefix pruner | Actual pruning and state persistence; exact retained-content hash, required instructions, and reduced byte size. | One controlled context fixture; downstream model-answer quality and child costs are unmeasured. |

## Repository checks and limits

`python -m skills.checkup.cli . --json` completed with exit 0. It reported
directives 100/100, infrastructure 24/100 and zero duplicate-function groups.
The isolated checkout has no local MCP wiring; that drift is not resolved by
this change. Taint scanning was unavailable in this runtime, so its zero count
does not establish a clean security scan. The diagnostic reported no at-risk
micro-models. No running homelab services were deployed or modified.

The generic skill-creator frontmatter validator rejects Conductor's existing
`layer: DECIDE` field. Botte uses this field for its registry and routing;
it was preserved. Repository-specific discovery, Conductor and MCP tests passed.
This is a documented compatibility limit of that generic validator.

`python scripts/test_readme_commands.py` passed 11 executable README checks
and skipped 11 environment-dependent examples before the parent integration.
The final local-link and staged pre-commit results are recorded below before
publication. The pre-commit script's JSON stage is only a placeholder; the
schema-validation evidence above comes from the actual JSON Schema tests.

`python scripts/pre-commit-check.py --fast` passed for the staged change:
seven Python files parsed, with no matching secret patterns. The local-link
check inspected 64 Markdown files and found zero broken links.
`git diff --cached --check` reported no whitespace errors.

## Tested source identity

These SHA-256 values identify the tested code, contracts and behavior tests.
They are reproducibility metadata, not signed attestations.

| File | SHA-256 |
|---|---|
| `skills/conductor/verified.py` | `d2fb2a143b1dba804d76261784a4795b18588459330e562fdb1ba92a6bb6dcd2` |
| `skills/conductor/cli.py` | `dad275db09a12cee2fc9b7c8f06436ebabf5793b5a946a14e6183b8e33d5b806` |
| `skills/conductor/__init__.py` | `e9b15c49cb32b65ebb539c65786e92906b6d892449c74e82d0203bf0f972fa4a` |
| `skills/llm_mcp/server.py` | `4872f17dc749c9939b8aa7683ac7abf234e7f6052256a9f1ce930489311a8e1d` |
| `skills/conductor/test_verified.py` | `30b1282e6b960e960fdcd661eca9f43412f13ff0e3c3d8609fb2464ee71eff05` |
| `skills/conductor/test_verified_pilots.py` | `72c62bac50f64398a79625876ad79c4a2b165bbb484273b689caab913ae2c8d8` |
| `docs/schemas/skill-plan.schema.json` | `b0641a5a06fb68b9a77a70f09aa900b40a1617b2165212418fc4cc370f9a61d1` |
| `docs/schemas/skill-run.schema.json` | `3ee547c3060997e9186951872e82f874bb0667bb416f3e5e1020d1165f354ef1` |
| `skills/conductor/effects.json` | `056f4d0f04b6a47d4f66aec4671fba79c76b1484b3797dc5c750d3ce6909b40b` |
