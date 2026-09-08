# Verification package for the mission stack

This change completes the five boundaries identified while reviewing PRs
#101–#103. It builds on #109 (`6c1424d0d2369e0db66b6d3a9e7425b30afa99ca`).
The review compares contracts with execution behavior; a local validation claim
or a passing unrelated check does not establish that a merge candidate is safe.

| Boundary | Enforced behavior | Regression evidence |
| --- | --- | --- |
| Mission plan | Validate a private copy at `execute`, including directly constructed plans. Commands, arguments, dependencies, mutation flags and evidence references must match the catalog; mutating steps require ACT. | `test_mission_boundaries`: unknown commands, command substitution, argument injection, forged flags/evidence/dependencies/status, changes after planning. |
| Independent review | #109 requires a distinct active reviewer lease whose base and head both equal the author head, plus an observed replay for each required proof. BLOCKED takes precedence over REWORK. | `test_review_boundaries`: wrong SHA, reused/expired lease, missing/unrelated proof, failure closure and approval precedence, real review CLI. |
| Committed handoff | Preserve dirty author worktrees in quarantine; never mark them READY_FOR_REVIEW. Fingerprint staged, unstaged and untracked Git-visible content. | `test_mission_boundaries`: tracked/untracked author edits, staged/content changes with unchanged status, symlink target text without reading the external file, quarantined resume rejection. |
| Context | Compile absent context from the actual leased checkout after selecting the base/resume SHA. Validate supplied manifests by regenerating all metadata from the normalized mission and those files. An explicitly empty manifest is invalid. | `test_mission_boundaries`: valid manifest, rehashed tampering, wrong mission, missing required file, dirty source checkout, real CLI resumption from an older commit. |
| Budgets | #109 checks capacity before dispatch and limits subprocess timeouts to remaining wall time. Explicit configuration may only tighten mission budgets. Revision counters remain durable and mission-bound. | `test_review_boundaries`, `test_mission_boundaries`, SAFE-EXIT tests: zero calls, deadlines, stricter/expanded configuration, concurrent registration, total and per-proof revision caps. |

## Reproduce

Use Python 3.10–3.12 in a fresh environment. Install the project and pytest;
pytest must be present so the three real reviewer CLI cases cannot silently
skip. The CI installation step includes it explicitly.

```sh
python -m pip install -e . pytest
python -m skills.meta_harness.test_mission_boundaries
python -m skills.meta_harness.test_review_boundaries
python -m skills.meta_harness.test_reliable_run
python -m skills.run_contract.test_run_contract
python -m pytest -q skills/safe_exit/test_safe_exit.py skills/meta_harness/test_safe_exit_integration.py
python scripts/run_tests.py -q
python scripts/pre-commit-check.py --fast
python scripts/test_readme_commands.py
python scripts/check_docs_links.py
python -m skills.checkup.cli .
```

Run the full runner on the combined tree containing #103 at
`e121ea16cbd5a772ddb485414928c0938eace2d5` and the hermetic ingestion test from
#104 (`2d77b5d2e93d9cd0e1c68f719dc3ac822abecbb2`). Preserve #103's newer
checkout-independent rules fingerprint fix when combining these sibling
branches. Run `python -m skills.directives_audit.test_rules` there too.

## Evidence needed for a merge decision

Record the candidate commit and tree, the intended base SHA and constituent
PR heads. Keep command exit statuses, test totals and skips, and links to the
workflow runs. The existing workflows target main; a green run for an older
head or sibling branch is not evidence for the combined candidate. A draft
integration PR targeting main can exercise the actual workflows without
merging the stack. Check its tested merge tree against the candidate tree.

The smallest package is the focused boundary tests, one full runner on that
combined tree, and the existing CI/checkup gates for the intended integration.
An independent code reviewer should inspect the authority, context, dirty-tree
and proof-coverage boundaries before any merge decision. Rebase, conflict
resolution or source changes invalidate the corresponding prior evidence.

## Compatibility and trust limits

Mission callers must use catalog plans. Callers may omit a context manifest to
compile it from the lease; supplied stale or forged manifests now fail closed.
Dirty work remains available for inspection and an explicit commit, followed
by a fresh proof run. Generated/ignored artifacts are outside the Git-visible
dirty fingerprint.

These are boundaries in the trusted local-runner API, not process isolation or
witness authentication. A subprocess inherits the runner's environment and
host permissions. Worker IDs, hashes and evidence labels do not authenticate a
remote reviewer or protect mutable local storage. The package establishes the
tested contract behavior; it does not authorize deployment, publication or a
merge, or substitute for validation on the intended host.
