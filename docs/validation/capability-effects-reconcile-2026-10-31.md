# Capability-effects reconciliation — 2026-10-31

This candidate preserves PR #108 head
`943a1ed00291193e155e4e9ab81fe74ef23708c7` and main
`53c67c39d0360c12e7e32bca989221f34f9790ec`. It does not activate a model,
install a host hook or change the authority of supplied plans.

## Conflict decisions

- Keep the current README command-timeout helper and bounded failure diagnostics.
- Preserve route-event provenance and current outcome handling, while retaining
  #108's removal of the false local-to-cloud escalation event.
- Combine bootstrap's installation-pinned hook and additive AGENTS.md creation
  with the effects, retry and partial-write documentation.
- Keep checkup's distinction between static MCP declarations, unknown runtime
  availability and model qualification, together with its side-effect limits.
- Preserve the current canonical runner and the ApproxSpatial and parallax suites from #142 and #143.

## Declaration review

Six existing declarations were reviewed against their changed implementations
before their source hashes were refreshed:

| Capability | Version | Reviewed behavior |
| --- | --- | --- |
| auto_router | 0.1.3 | Event provenance labels remain declarations; semantic-cache hints use v2 features and abstain on incompatible weight schemas without replacing weights. |
| bootstrap | 0.2.0 | New hooks pin their installation; existing hooks remain; missing AGENTS.md can link existing CLAUDE.md. |
| checkup | 0.4.0 | MCP project-file/launcher inspection is static; local learning sample counts never prove activation readiness. |
| infra_advisor | 0.4.0 | MCP declaration recognition delegates to the static inspector, without starting servers or proving connectivity. |
| preflight | 0.2.0 | Bounded selective Parcimonia guidance, explicit abstention and separate policy writes replace the old blanket-hook description. |
| trajectory | 0.1.1 | Outcome/advice events identify their declared producer and component kind without authenticating evidence. |

The checkup declaration additionally binds `mcp.py`; preflight additionally
binds `assessment.py`. Imported dependencies and runtime evidence retain the
limits documented in each declaration. All 19 present declarations validate as
`declared`; that status still means matching identity and source bindings only.

## Reproduced hook defect

The current hook defined its guidance table twice. The second assignment
discarded the specific statistics, exact-file-duplicate and local-link guidance.
Three behavioral subcases failed before removing that duplicate assignment,
then passed. The full preflight suite passed 19 tests. The correction restores
existing advice and adds no new intent or execution path.

## Runner regression

Inserting new suites before e2e exposed an existing positional assumption in
changed-file selection. The current nine-test runner-verdict suite failed 12
subcases before correction. Selection now locates e2e by label, preserving the
cross-cutting suite regardless of registration order; all nine tests passed.

## Validation scope

On Python 3.12, 25 relevant registered suites passed 464 tests across effects,
observation/evidence, routing, bootstrap, preflight, checkup and trajectory.
The 12 loopback network-observation tests initially encountered a sandbox
socket restriction; running that same isolated suite with loopback sockets
available passed all 12. No external endpoint or model was used for those tests.

The subsequent main updates added only the ApproxSpatial and parallax files
and their runner entries. All 17 tests passed after clean merges (nine
ApproxSpatial, eight parallax), and the earlier tested module implementations
remained unchanged. These observations are targeted
local evidence, not the complete CI matrix. Hosted checks must be associated
with the published candidate revision before integration.

The final main also contains #69 and #99. The portfolio addition is independent.
The semantic-cache v2 delta was reviewed through the hint wrapper, feature
schema guard and model loader before updating the AutoRouter declaration.
Historical semantic weights remain unchanged; incompatible schemas cause
abstention, not qualification or replacement. Final targeted checks passed 184 tests across seven suites covering routing,
effects, outcome adaptation, candidate guards, runner selection and checkup.
All 19 effects declarations remained current after the composition.
