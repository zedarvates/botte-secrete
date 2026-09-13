---
name: effect-review
description: Review a selected operation's likely consequences and its execution evidence, or assess a concrete reuse proposal. Use with Conductor review cues or a task handoff; this supplies a shared review method and does not execute the operation.
---

# Review consequences in context

Use this method once for the relevant workflow. Keep capability-specific facts
in the selected skill and its optional `effects.json`.

## Before the action

Read the selected skill's complete instructions. Match its suitable cases,
exclusions and prerequisites to the actual command, arguments, resources and
existing task scope. A lexical match or declaration status does not establish
applicability.

Start with Conductor's `review_before`. It is a compact index: operation-specific
assessment is deferred. Read the relevant sections of that source's `effects.json`
for expected changes, downstream dependencies and recovery/retry conditions.
Fetch just those details with MCP `effect_details`: copy `source` and
`declaration_sha256` from the review into `source` and `expected_sha256`, then
request selectors such as `/retry` or `/expected_effects/0`. CLI/Python equivalents
are in the [detail-reading guide](../../docs/capability-effects.md#read-deferred-details).
Require `selection_status: selected`; a changed or unavailable declaration or
missing entry returns no fragments. Refresh the review and reassess changed
conditions before combining detail reads. Array indexes belong to that digest.
The capability-wide reversal/retry labels may cover several different operations.
Missing, invalid or stale declarations call for checking the relevant source;
they do not create a new approval requirement. An empty attention list is not a
safety verdict. Resolve material uncertainty proportionally to the actual task.

## After the action

Use `review_after` and the step result. When present, inspect the referenced
`effects_observed` companion for affected resources, unfinished work or deviations.
Process success, a written file and HTTP 200 support different, limited facts.
State what is verified, what remains unknown and the next useful action.

Before a dependent step, check the prerequisite result it actually needs. After
interruption, inspect current state and still-active operations before retrying;
retain completed work. The Conductor does not enforce all such dependencies or
provide rollback. These cues never grant permission or restart work themselves.

## Reuse and improvement

Assess reuse when there is a concrete target: what transfers, what must change,
and which target-context check supports it. Link evidence to the capability
version and run context; do not promote reuse from a successful exit alone.
Compare a proposed improvement with the current version on representative tasks,
including failures and context cost, before generalizing the result.

Keep the handoff proportional: verified result, evidence reference, material
uncertainty and next action. Routine checks can stay deterministic; this method
does not require another LLM call for every tool use.

For CLI/Python/MCP integration and evidence limits, consult the
[common contract](../../docs/capability-effects.md#compact-shared-review).
