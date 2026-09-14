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
- Candidate identity is available as source/build/tested commit SHA, or exact Git
  tree identity when a CI provider tests a synthetic PR merge commit.
- Private holdout evidence is generated outside the builder-visible repository.

## Agent roles

Factory Assurance does not turn every agent into a generic worker. Existing
Botte roles remain specialized:

- `conductor`: composes/coordinates the plan; it is not the routine final judge.
- Blue Team / Mousquetaires: Porthos audits, d'Artagnan builds fixes, Aramis
  optimizes, Athos coordinates/consolidates the Blue side.
- Red Team / Cardinal: Rochefort counter-audits, Milady hunts regressions from
  changes, Comte de Wardes challenges optimizations, Cardinal coordinates and
  synthesizes the adversarial verdict.
- `gauntlet`: independent evidence/compliance/regression judge when used by a
  factory run.
- `monte_cristo`: strategic outsider for shared-assumption challenges; it does
  not become a routine builder or evidence judge.
- external/local workers are allowed, but builder and judge identities must stay
  distinct.

These roles are governance declarations, not execution credentials. No role
entry grants authority to mutate a repository, merge, deploy, publish, purchase,
or activate a model.

## Input contract

The JSON run record contains:

- `mission`: goals, invariants, non-goals, forbidden transformations and an
  explicit `within_mission` decision.
- `actors`: separate `builder` and `judge`, plus optional `orchestrator`.
- `effects`: declared, observed and unresolved effects.
- `evidence`: named required/optional checks and their status.
- `controls`: positive control, negative/mutation control, private holdout scope,
  historical regressions and adversarial cases.
- `identity`: `source_sha`, `build_sha`, `tested_sha`, optional matching
  `source_tree`/`build_tree`/`tested_tree` for synthetic PR checkouts, and
  optional `deployed_sha`.
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
2. Known named agents must be assigned only to compatible factory roles.
3. Undeclared observed effects block promotion.
4. Required evidence must pass.
5. The positive control must pass.
6. The negative/mutation control must fail, proving the gate can detect a defect.
7. Holdout material must remain private/external to the builder-visible repo.
8. Exact commit identity is preferred. When GitHub Actions tests a synthetic PR
   merge commit, exact source/build/tested Git tree identity is required instead;
   tree equality proves repository content, not commit ancestry.
9. Merge and deployment identities remain separate; a deployment SHA is checked
   only when supplied.
10. Historical and adversarial corpora are warnings in v1, not invented proof.

## Invocation

```bash
python -m skills.factory_assurance.cli examples/factory-assurance/run.json --pretty
python -m skills.factory_assurance.test_factory_assurance
python -m skills.factory_assurance.test_integrations
python -m skills.factory_assurance.test_roles
```

The real StoryCore PR #57 shadow fixture intentionally returns `hold` until its
private holdout and negative mutation evidence actually exist:

```bash
python -m skills.factory_assurance.cli examples/factory-assurance/storycore-pr57-shadow.json --pretty
```

## Non-goals

- No automatic merge.
- No automatic deployment.
- No secret material in the repository.
- No claim that a public `holdout/` directory is private.
- No LLM-based verdict inside the final evidence gate.
