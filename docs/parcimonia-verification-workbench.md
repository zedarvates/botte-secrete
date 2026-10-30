# Parcimonia verification workbench

Unreleased 1.11.0 candidate, local Python runtime. Six capabilities are usable
through `botte verify` (or `python -m skills.app_test.workbench`). The cloud
helpers do not acquire process execution or access to the user's machine.

| Capability | Entry point | Evidence and limit |
| --- | --- | --- |
| Reduce a reproduction | `botte verify reduce` | Explicit JSON subprocess oracle, same failure fingerprint, final replay; no global-minimum guarantee. |
| Order tests | `python scripts/run_tests.py --prioritize -q` | Uses observed command-bound failure/time history, retains every selected suite; heuristic, no promised speedup. |
| Compare cloud/local | `botte verify conformance --cloud-root PATH` | Actually executes supplied Python/Node sources, reports both versions and source hashes; not a live service test. |
| Challenge tests | `botte verify mutate` | Bounded Python token mutations in disposable copies, passing baseline required; survivors can be equivalent mutants. |
| Explore an interface | `botte verify explore` | Explicit adapters, reset/replay, bounded allowed actions; local HTML navigation and model replay are separate. |
| Triage intermittent failures | `botte verify triage` | Fixed seed/context, all attempts retained; finite observations do not establish future reliability. |

## Reproduction and intermittent-failure adapters

Create a JSON file containing trusted local argv, for example
`["python", "/absolute/path/to/oracle.py"]`. Shell expansion is not performed.
The command consumes one JSON value on stdin, prints one JSON object, and exits
0 when it successfully reports an observation. A process crash or malformed
response is incomplete evidence, not a reproduction of the target defect.

For reduction, stdin is a candidate list. Return `{"status":"failed",
"failure_fingerprint":"BUG-ID"}` only for the target failure, or
`{"status":"passed"}` when it does not occur. Other failures need different
fingerprints. The original input file is preserved.

```sh
botte verify reduce --input trace.json --command-file oracle-command.json --max-calls 64 --max-seconds 30
```

For triage, stdin is `{attempt,seed,context_sha256}`. Return `status` as
`passed`, `failed`, `incomplete`, or `not_run`; failed observations should supply
`failure_signature`. A returned context fingerprint must match the fixed one.

```sh
botte verify triage --command-file oracle-command.json --context environment.json --seed 17 --attempts 5
```

Both commands retain indexed subprocess observations: command fingerprint,
observed exit, elapsed time and bounded-output hashes. Per-process timeout is
enforced by the CLI adapter; arbitrary Python callbacks have a cooperative
deadline. Capturing output in temporary files is not a disk quota or an OS
sandbox. Commands and source checkouts must be trusted test code.

## Mutation and exploration

Mutation copies only the named source, tests and optional support paths, then
changes one supported comparison, boolean or integer token. Other bytes,
including comments and licence headers, are preserved. The built-in command
adapter requires actual nonempty `unittest` completion; other frameworks need
an explicit Python runner adapter. Import errors, all-skipped tests, missing
results and timeouts do not kill a mutant.

```sh
botte verify mutate --project ./test-project --source subject.py --tests test_subject.py --max-mutants 12
```

Exploration requires `reset`, `observe`, and `perform` adapter operations.
`DeclarativeAdapter` accepts `{scope,initial_state,states}` with per-state
`actions` mapping action IDs to target IDs; reports say `model_replay`.
`LoopbackHttpAdapter` actually reads HTML from an explicit literal loopback IP,
with exact allowed paths, no redirect and no proxy. Each page declares
`parcimonia-state` and `parcimonia-scope` meta tags; allowed links use
`data-action`. Forms, JavaScript, screenshots and native desktop controls are
not provided by this HTTP adapter.

```sh
botte verify explore --origin http://127.0.0.1:8000/ --scope demo --paths paths.json --actions actions.json --goals goals.json
```

Paths/actions/goals are JSON arrays. Replays count against the action budget.
`completed` means the allowed observed frontier was exhausted; global coverage
and graphical qualification remain unknown/false. Unobserved goals are not
declared unreachable in the entire application.

## Test order and conformance

The canonical runner's opt-in `--prioritize` stores bounded observations in its
existing local cache. Prior failing checks run before unseen checks, then
historically passing checks run shortest first. Commands have exact fingerprints;
history from a changed command is not reused. Invalid history falls back to the
original order and is preserved. No selected check is removed and no old result
is promoted into current test evidence. `--changed` still means a partial suite.

The pure `botte verify prioritize --input checks.json` accepts a checks list
`[{label,command}]` and optional `history`; it proposes order without execution.

Conformance covers assessment, GitHub planning and supplied-evidence compaction.
The common projections preserve JSON types and missing/null differences.
Implementation-specific ranking and corresponding shortlist metadata are
explicitly excluded; shortlist safety invariants are still checked. One authored
integral-float boundary is allowed only against a normalized reference. This is
not permission to ignore other divergences. Statistics in a separate Python
candidate are explicitly outside this comparison.

## Status and demonstration

CLI exits: reduction 0 only for freshly preserved failure, otherwise 2; triage
1 for any reported failure, 0 for no failure observed, otherwise 2; mutation
1 for survivors, 0 only for completed no-survivor/no-inconclusive campaigns,
otherwise 2. Exploration 0 means completed frontier, 1 observed transition
failure, 2 incomplete. Conformance 0 means matching declared projections with
known differences listed, 1 unexpected mismatch, 2 unavailable/incomplete.
None of these zero exits proves application correctness.

Run the [authored demonstration](../examples/parcimonia_verification_demo.py) with
`--help` for a fresh output directory and an optional cloud source checkout.
It records actual subprocess and HTTP fixture observations, not a real user
incident, GUI run or acceleration benchmark. See the
[knowledge inventory](parcimonia-knowledge-inventory.md) for existing wiki,
memory, RAG/DAG, graph and LLM components and their documentary links.
