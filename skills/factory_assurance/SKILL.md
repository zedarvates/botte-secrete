# Factory Assurance Layer

## Purpose

Use this skill after routing/planning/execution and before any promotion decision.
It converts agent claims into a deterministic evidence decision. It does not build
the change and it does not grant merge or deployment authority.

## Preconditions

- A bounded action has a mission contract.
- The builder and independent judge identities are known.
- Expected effects are declared before judging observed effects.
- Required evidence has machine-readable pass/fail state.
- Candidate identity is available as source/build/tested commit SHA.
- Private holdout evidence is generated outside the builder-visible repository.

## Input contract

The JSON run record contains:

- `mission`: goals, invariants, non-goals, forbidden transformations and an
  explicit `within_mission` decision.
- `actors`: separate `builder` and `judge`.
- `effects`: declared, observed and unresolved effects.
- `evidence`: named required/optional checks and their status.
- `controls`: positive control, negative/mutation control, private holdout scope,
  historical regressions and adversarial cases.
- `identity`: `source_sha`, `build_sha`, `tested_sha`, and optional
  `deployed_sha`.
- `stage` / `requested_autonomy`: at most bounded; unbounded autonomy is refused.

## Output contract

`status=review_ready` means only that the deterministic evidence package is
complete enough for independent human review.

The layer always emits:

- `may_merge_automatically=false`
- `may_deploy_automatically=false`

A blocker yields `status=hold` and `repair_evidence_and_re_evaluate`.

## Trust boundaries

1. Builder and judge must be distinct.
2. Undeclared observed effects block promotion.
3. Required evidence must pass.
4. The positive control must pass.
5. The negative/mutation control must fail, proving the gate can detect a defect.
6. Holdout material must remain private/external to the builder-visible repo.
7. `source_sha == build_sha == tested_sha` is mandatory before review readiness.
8. Merge and deployment identities remain separate; a deployment SHA is checked
   only when supplied.
9. Historical and adversarial corpora are warnings in v1, not invented proof.

## Invocation

```bash
python -m skills.factory_assurance.cli examples/factory-assurance/run.json --pretty
python -m skills.factory_assurance.test_factory_assurance
```

## Non-goals

- No automatic merge.
- No automatic deployment.
- No secret material in the repository.
- No claim that a public `holdout/` directory is private.
- No LLM-based verdict inside the final evidence gate.
