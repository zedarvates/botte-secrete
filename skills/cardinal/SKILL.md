---
name: cardinal
description: Review Blue Team audit, fix and optimization results using scoped counter-reviews, or consolidate existing Blue/Red reports. Use when a task needs adversarial review of proposed changes or a report-based confrontation summary.
---

# Cardinal — review changes and consolidate findings

## Select the operation

For an orchestrated review, use [core guidance](../core-agent.md) and only the
relevant role prompt: [Rochefort](prompts/rochefort.md) for missed audit findings,
[Milady](prompts/milady.md) for regressions, [Comte de Wardes](prompts/comte_de_wardes.md)
for over-optimization, or [Cardinal](prompts/cardinal.md) for coordination.
Delegation, model calls and tests depend on the host and the existing task scope;
the confrontation script itself does not launch agents, execute suggested commands,
repair code or contact model providers.

To consolidate reports already produced:

```bash
python skills/cardinal/scripts/cardinal_confront.py <blue_reports_dir> <red_reports_dir>
```

| Required file | Minimum input accepted by the script |
|---|---|
| Blue `audit/audit-report.json` | Non-empty JSON object. |
| Blue `fix-report.json` | Non-empty JSON object. |
| Blue `optimize/optimization-plan.json` | Non-empty JSON object. |
| Red `counter-audit.json` | `false_negatives` and `underestimated`: lists of objects. |
| Red `counter-fix.json` | `regressions` and `incomplete_fixes` (or prompt alias `incomplete`): lists of objects. |
| Red `counter-optim.json` | `over_optimizations` and `wrongly_excluded_skills` (or prompt alias `wrongly_excluded`): lists of objects. |

If both aliases are supplied, their values must agree. Explicit empty finding
lists are accepted; do not invent an empty review to represent a stage that
did not run. A missing/malformed report or required findings field returns exit
code **2**, with no new verdict or report write. An earlier `confrontation.json`
is preserved and must not be mistaken for this failed run's output.

## Consequences, evidence and reuse

Read [effects.json](effects.json). A complete input set produces stdout and
replaces `<red_reports_dir>/confrontation.json`. Preserve a useful prior result
before rerunning. There is no multi-file snapshot, output transaction or lock.
Reports can contain source paths and finding descriptions; review their audience.

The score is a weighted count of six supplied finding categories. Blue reports
receive only a presence/object check; the script does not compare their claims
against source, authenticate reviewers or prove that tests ran. Other counter-report
categories are not included in the score. A zero exit means consolidation
completed, including for an unfavorable verdict; it is not a quality gate.

Use evidence from the reviewed checkout, actual tests and counter-review coverage
before acting on the summary. On failure, reconcile inputs and any existing output
before retrying. Reuse in another pipeline needs explicit field mapping, omission
handling and target-specific acceptance criteria. Keep predictions, observations
and unverified claims separate in the task report; see the
[common contract](../../docs/capability-effects.md).
