# External pilot protocol

Purpose: let external open-source peers exercise Botte Secrete / Factory Assurance on their own projects without presenting our tool output as a certification of their code or as a substitute for their own verification.

## Core disclosure

Every external pilot invitation must say, in substance:

- this is a test of **our own tooling** on a real external project;
- findings are experimental and may be wrong, incomplete, or irrelevant;
- maintainers should reproduce every material claim with their own tests/review;
- Botte Secrete does not grant merge, release, deployment, security, licence, or quality approval;
- no automatic write, merge, deployment, publication, model activation, or destructive operation is requested;
- maintainers may decline, narrow, or stop the pilot at any time.

## Preferred pilot shape

1. Choose a public, bounded, non-destructive target issue/PR or a read-only repository snapshot.
2. Record the target commit/tree and the exact scope agreed by the maintainer.
3. Run Botte Secrete in `observe`, `consultative`, or `shadow` mode first.
4. Separate builder from judge. If no build is requested, run review/assurance only.
5. Treat all tool findings as hypotheses until independently reproduced.
6. Never ask the maintainer to trust our CI, mutation, holdout, security, performance, or quality claims without their own verification.
7. Share a compact consequence report: what was inspected, what was observed, evidence references, limits, and what remains unknown.
8. Do not publish private holdout cases, credentials, prompts, local paths, or proprietary project data.

## Suggested first collaborators

### Cole Medin / AI Software Factory

Good fit: compare Factory Assurance with an AI software-factory workflow on a bounded issue or PR. The useful experiment is not "which factory wins"; it is whether independent evidence, mutation controls, exact candidate identity, and explicit consequence reporting catch problems that ordinary green CI misses.

Suggested boundary: read-only/shadow first; no merge/deploy. Cole and collaborators rerun their own tests and decide independently whether any observation is valid.

### Stefan Vaskevich / Stefan 3D AI (@Stefan_3D_AI)

Good fit: 3D/game asset and geometry workflows where visual/structural correctness can diverge from conventional tests. A pilot should combine deterministic asset/mesh checks with Stefan-side visual inspection and his own Blender/Unreal/Unity/tool tests.

Suggested first scope: one public asset or bounded 3D workflow, read-only/shadow, with explicit geometry/material/rigging checks and no claim that Botte's result replaces artistic or engine-side validation.

## Public invitation wording

Keep outreach short, transparent, and non-promotional. Do not imply endorsement, affiliation, or prior agreement.

Example:

> Hi — I am testing an open-source, evidence-gated agent orchestration project called Botte Secrete / Factory Assurance. I would be interested in running a small read-only or shadow pilot against one bounded part of your project, mainly to test our own tooling on a real external codebase or asset workflow. Any findings would be experimental, and you should reproduce/verify them with your own tests and review before relying on anything we report. We would not merge, deploy, publish private data, or activate anything on your behalf. If that sounds useful, I can keep the pilot narrow and send back the exact evidence and limits rather than a generic AI review.

## Success criteria

An external pilot is useful even when Botte Secrete is wrong. Measure:

- true findings confirmed by maintainer tests;
- false positives / false holds;
- defects missed by public CI but caught by independent checks;
- mutations the gate fails to catch;
- ambiguity in effects/consequences;
- cost and latency;
- amount of maintainer correction required;
- whether the result was reproducible independently.

No external pilot result automatically raises autonomy for other repositories or operation classes.
