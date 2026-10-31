# Six verification capabilities and knowledge inventory

Date: 2026-10-30. Candidate 1.11.0, based on draft PR 152 at
`992947158fb1b7e291cb2407158fac8964729d21`. These are local Python runtime
capabilities and plugin guidance, not a redeployment of cloud service 0.5.0.

## Executed checks

`BOTTE_CONFORMANCE_CLOUD_ROOT=/explicit/cloud/checkout python scripts/run_tests.py --prioritize -q`
completed with **1341 passed, 0 failed, 76 suites**. The selected suites were
all retained. The external source path was supplied explicitly, so the real
conformance qualification was executed rather than skipped. Without a supplied
cloud checkout that one qualification is explicitly skipped and is subtracted
from the workbench pass count. The fixture-based conformance tests still run.

The reviewed authored demonstration executed six cases with **34 independently
checked assertions**:

| Case | Observed result |
| --- | --- |
| Reproduction reduction | Actual JSON oracle subprocess, five list items reduced to CONNECT/CLOSE, same fingerprint freshly reproduced; original input retained. |
| Test ordering | Three actual child checks observed and all three replayed in proposed order; observed failure scheduled first, none omitted. |
| Cloud/local conformance | Actual Python/Node sources: 21 matched outputs, 10 matched rejections, 1 explicitly declared integral-float difference, 0 unexpected mismatch. |
| Mutation | Real unittest baseline passed; two survivors detected in an intentionally weak test, expected CLI exit 1; original files unchanged. |
| Interface exploration | Real allowlisted loopback HTML application, four states/four edges independently asserted, help dead end and done goal observed; no graphical claim. |
| Intermittent-failure triage | Four actual subprocesses, two failures/two passes retained in order with fixed seed/context; expected finding exit 1. |

Missing cloud source produces a partial demonstration and exit 2. Reusing an
output directory is refused without changing its report. Demonstration fixtures
are authored examples, not historical user incidents or a performance holdout.
Helper, source and fixture hashes, commands, exits and comparison exclusions
are recorded in the generated report. Sources remained unchanged during replay.

README command checks: **11 passed, 0 failed, 10 intentional skips**. Local
documentation links passed. Independent review executed separate probes for
the reducer, fixed-context triage, CLI exits, real HTTP failures, semantic cloud
drift, runtime crashes and mutation false-credit cases.

A fresh wheel was installed with declared dependencies in a new virtual
environment. **33 installed-runtime checks passed** on Linux/Python 3.12,
including `pip check`, module identity and installed `botte verify` commands
run outside the source checkout without injected `PYTHONPATH` or HOME override.
Actual reduction, intermittent triage, model exploration, mutation, priority and
32-case conformance commands retained their expected finding/incomplete exits.
This is runtime installation qualification, not installation into the Codex host.
Packaged inputs remained unchanged during qualification.

Wheel SHA-256:
`24f234ac0ddcab3ee3d96defc9309261c76bf31de0043883b76469b8278da26d`.
Packaged-source manifest SHA-256:
`da05f7c747068066e55e6f80fa1f8cf07210047d4fb49b04ec552638a54d70b7`.
All 21 changed/new Python files parse with Python 3.10 grammar. All 77 Markdown
files have valid local links. Project checkup completed; its source-checkout
MCP declaration result does not establish installed-host availability.

## Corrections prompted by independent review

- Mutation now edits exact source tokens. An SPDX-header-only test had falsely
  killed reformatted mutants; the unchanged witness now reports survivors.
- Selected-directory entry/depth/time limits prevent unbounded traversal.
- CLI process identity, termination evidence and output hashes remain in indexed
  observations after domain-specific normalization.
- Special JSON/history files are refused before blocking reads; oversized
  numeric values are rejected before float conversion.
- Required test selection and historical scheduling evidence remain separate.
  An old pass is never used as a current test result.

## Knowledge and execution scope

The [knowledge inventory](../parcimonia-knowledge-inventory.md) was checked
against current source and private documentation, with public links pinned to
observed revisions. Existing Memory Hub, capability/audit graphs, DAG helpers,
pipeline definitions and local LLM client are distinguished from experimental
Parcimonia memory/retrieval branches. Private corpus contents and Space links
are not copied into public source.

These checks qualify trusted local test adapters, authored fixture behavior and
the specific source combinations. Python callback deadlines are cooperative;
process adapters add per-call timeouts. Temporary copies are not an OS sandbox.
No real desktop GUI, game, live wiki engine, LM Studio model, billed usage,
general accuracy or end-to-end acceleration was qualified by this increment.
Equivalent mutants remain possible; finite exploration is not global coverage.
