# Missions, reviews and accepted results

This workflow connects the existing completion verifier, explicit Conductor
plans, Parcimonia's recipe evaluation and the current Kanboard/Odin mission.
It does not add a scheduler or replace the source of truth. Tools are opt-in;
committing this guide does not install a plugin or change a workstation.

## Before execution

Reuse the task ID and current source revisions. State the expected result as
identified criteria with a verifier, input identity and evidence scope. An
agent finishing a turn is not acceptance. Keep unresolved effects and unavailable
checks visible; do not replay an operation with an unknown result.

Choose review effort from impact, reversibility and uncertainty. Give a reviewer
the intended behavior, scope, exact diff/base and raw evidence without telling
it the desired verdict. A requested, queued, interrupted, failed or quota-limited
review is incomplete. A completed review still does not attest its findings;
reproduce material findings against the candidate being accepted.

## Verify each required result

Use [mission criteria](integrations/verified-mission.md) for a task containing
multiple checks. It composes the existing v1 receipt verifier and requires
externally pinned evidence. Use `python -m skills.cli completion-proof --help`
for the installed command interface. Source or input changes invalidate affected
evidence; a success from another task cannot discharge this task's criterion.

## Measure through acceptance

Use Parcimonia's `agent_recipes` workflow helpers for review planning, explicit
review status, accepted-result cost and candidate replay. Include preparation,
attempts, reviews, retries and fallback. Keep elapsed duration separate from
summed work time when work overlaps; retain human intervention separately. Missing
usage or financial data stays unknown, and zero model calls inside a helper is
not a measurement of the host's token use.

Evaluate a recipe change on retained episodes and separate held-out cases with
the same acceptance criteria. Record failures and source/version identity.
Comparison produces review evidence, never automatic promotion of a skill,
model or routing policy.

## Close the work

Link the result and review to the task and its exact revision. Inspect the
[worktree lifecycle](worktree-lifecycle.md) before proposing cleanup. The
inventory preserves dirty, active, unknown and unmerged work; it does not remove
directories, branches or history. Existing authorization governs any later
destructive operation.

## Ultimate Odycer pilot

The first gameplay acceptance case requires two distinct real clients:
connection, spawn, movement, NPC interaction, shared state and reconnection.
Verify movement in both directions, an authoritative NPC response and no
duplicate entity after reconnection. Bind server, client and gateway revisions
and the actual configuration to the run. Tests of a proof validator or a mock
transport qualify only that validator or mock. An unavailable canonical server
keeps the real multiplayer pilot blocked.

## Provenance

Adapted after reviewing David Ondrej's public
[Goal Loop](https://github.com/davidondrej/skills/blob/main/skills/agent-orchestration/goal-loop/SKILL.md),
[GPT Review](https://github.com/davidondrej/skills/blob/main/skills/agent-orchestration/gpt-review/SKILL.md)
and [Risky Changes](https://github.com/davidondrej/skills/blob/main/skills/ops-and-setup/risky-changes/SKILL.md).
The linked video was not visually inspected and its full transcript was not
available. These adaptations are not a reproduction of its performance claims.
