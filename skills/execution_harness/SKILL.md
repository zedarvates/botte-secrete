---
name: execution-harness
description: Record requested versus executed state, evidence, consequences, recovery points, divergent exploration, independent verification, and model-by-harness capability observations without executing consequential actions itself.
license: MIT
---

# Execution Harness

Use this skill when an agent workflow needs an auditable envelope around work
performed by deterministic tools, local models, cloud models, or other agents.
It is a **contract and verification layer**, not an executor and not an
authority escalation mechanism.

## Choose it when

- a task can degrade because of hardware, budget, context, or availability;
- several agents should explore independently before sharing findings;
- candidate artifacts need a protected last-known-good state;
- a handoff must state what completed, what remains, what changed, and what is
  still uncertain;
- model performance is being compared across different harnesses or hardware;
- commercial workflows must distinguish reusable code/architecture from model
  weights carrying non-commercial restrictions.

Do not use it as a substitute for domain-specific validation. A passing harness
record only means the declared invariants were respected; it does not prove the
underlying scientific, security, artistic, or product claim.

## Required execution record

Capture, when applicable:

1. mission and immutable-enough context snapshot;
2. capabilities actually available and constraints in force;
3. requested execution state and actual execution state;
4. every material delta between those states, with reason and acknowledgement;
5. evidence references and whether they were independently verified;
6. artifacts and their digests;
7. consequences on touched resources, including reversibility;
8. uncertainties and unresolved evidence;
9. last-known-good recovery point;
10. remaining work and a bounded handoff.

## No silent degradation

If `requested_state != executed_state`, the workflow must record an
`ExecutionDelta` with a non-empty reason and explicit acknowledgement. Running a
shorter, cheaper, lower-quality, different-model, reduced-context, or otherwise
altered job and presenting it as the requested job is invalid.

A workflow may still choose a degraded path when policy permits it; it must say
what changed. This rule is intentionally inspired by mature workflow skills that
make resource-driven fallbacks explicit rather than silently changing the task.

## Last-known-good rule

Treat new output as a candidate. Promote it to the recovery point only after
verification evidence exists. A failed candidate remains useful experimental
evidence but must not replace the last-known-good artifact.

## Divergent exploration

For high-uncertainty work, prefer:

`isolated exploration -> evidence gate -> cross-pollination -> independent verification`

Agents should not receive each other's hypotheses during the isolated phase
unless the task explicitly requires collaboration. Only candidates with evidence
and a passed evidence gate enter the cross-pollination packet. A producer cannot
serve as its own independent verifier.

This mode complements, rather than replaces, the existing strategic outsider,
red-team, and domain-specific verification paths.

## Capability Atlas

Record observations by at least:

`task x model x harness x hardware x quantization`

and attach evidence references. Latency, quality, outcome, and failure mode are
observations, not universal properties of the model. Never collapse two results
that used materially different harnesses into a model-only benchmark.

The initial implementation is deliberately in-memory and serialization-friendly.
Persistence should reuse the repository's established bounded/local data stores
rather than introduce a second memory authority.

## Commercial licence boundary

Keep code/architecture reuse distinct from weight usage. Non-commercial model
weights must not be promoted into a commercial execution path merely because the
surrounding implementation is permissively licensed. Record the actual weights
licence in the execution context and fail closed when commercial use conflicts
with it.

`validate_commercial_weights_policy` checks a caller-supplied declaration. For
commercial use, it recognizes `NonCommercial` and `BY-NC` across case, whitespace,
hyphen and underscore variants. It rejects empty declarations and placeholders
`unknown`, `unspecified`, `unqualified`, `tbd`, `n/a`, `none` and `NOASSERTION`.

Treat a return without an exception only as absence of those declared blockers,
never as legal clearance. Qualify the actual weight terms against their sources
before any future use, including custom terms and licence expressions: this
helper performs no licence discovery or permission verification. With
`commercial_use=False`, it makes no rights decision either.

## Asymmetric budget guidance

Context ingestion, retrieval, deliberation, and final generation need not use the
same resource class. Prefer cheap deterministic/context-compaction stages first,
then spend larger-model or cloud budget only when verification, uncertainty, or
output quality justifies it. Record the selected path and any divergence from the
requested execution state.

## Current boundary

Version 1 exposes contracts only. It does not automatically route, execute,
persist Atlas observations, activate models, modify memory permissions, promote
artifacts, or merge code. Integration with existing router, local harness,
trajectory, memory, and handoff surfaces should happen incrementally behind their
existing policy gates.
