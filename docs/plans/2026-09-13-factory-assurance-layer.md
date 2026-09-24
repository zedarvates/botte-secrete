# Factory Assurance Layer — implementation plan

Status: first executable slice, no automatic promotion.

## Why

Botte Secrète already routes work toward the cheapest verifiable path. The
Factory Assurance Layer closes the gap between "an agent says it worked" and
"the evidence package is safe to present for promotion".

The layer sits after capability/skill routing and execution:

`mission -> plan -> builder -> independent judge -> assurance -> human review`

## v1 implemented here

1. **Mission contract** — positive goals plus invariants, non-goals and forbidden
   transformations.
2. **Independent judge boundary** — builder and judge identities cannot match.
3. **Effect reconciliation** — observed effects outside the declared set block.
4. **Evidence contract** — required evidence must pass.
5. **Positive + negative controls** — a healthy candidate must pass and a known
   bad/mutated candidate must fail.
6. **Private holdout boundary** — the run record must attest that holdouts are
   external to the builder-visible repository. The secret scenarios themselves
   are deliberately not committed.
7. **Exact-candidate identity** — source, build and tested SHA must match.
8. **Consequence handoff** — blockers/warnings/next action are returned as a
   stable JSON decision.
9. **Promotion boundary** — even a complete package returns only
   `review_ready`; automatic merge and deployment stay false.
10. **Experience hooks** — historical-regression and adversarial-corpus checks
    are represented now and remain warnings until real corpora exist.

## Autonomy ladder

The accepted ladder is:

`observe -> consultative -> shadow -> gated -> bounded`

There is intentionally no unbounded `autonomous` mode in v1. Higher autonomy
must be earned per operation class, not granted repository-wide.

Suggested policy:

- documentation-only, deterministic and reversible: may eventually reach bounded;
- normal source changes: gated;
- network/auth/security/infrastructure changes: consultative or shadow;
- destructive operations, secrets and irreversible external actions: human gate.

## Private holdouts

Do not create `holdout/` in this public repository and call it secret. A future
controller should mount or fetch private holdout cases at runtime into a
restricted location inaccessible to the builder. Only the summarized outcome,
scenario-set version/digest, and judge evidence should enter the run record.

## Exact identity

For pre-merge proof:

`SOURCE_SHA == BUILD_SHA == TESTED_SHA`

For deployment proof, add:

`DEPLOYED_SHA == SOURCE_SHA`

Merge and deployment remain separate workflows.

## Pilot ("dark lap")

Use one bounded non-critical issue in a target repository:

1. triage and mission check;
2. choose cheapest capable route;
3. builder makes the change;
4. a different judge evaluates it;
5. run targeted/public tests;
6. run externally stored private holdouts;
7. inject a controlled mutation and verify the gate fails;
8. bind all proof to the exact candidate SHA;
9. emit a consequence report;
10. stop at human review — no merge.

Measure latency, compute/model cost, escalation count, false approvals, false
holds, unexpected effects, and human corrections. Only then consider raising
autonomy for that operation class.

## Next integration slices

- adapter from existing capability/effect manifests into this run record;
- signed/digested external holdout manifests without revealing scenarios;
- reusable mutation operators per language/repository;
- historical-failure corpus sourced only from verified incidents;
- controller service profile for Eurekai and worker registration for other hosts;
- dashboard view showing assurance status and identity chain;
- deployment verifier that compares runtime `/build-id` to the approved SHA.

These are intentionally not claimed as implemented by v1.
