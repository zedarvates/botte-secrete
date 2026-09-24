---
name: control_loop
layer: GOVERN
description: Inspect routing telemetry and propose, apply or reset effort-to-tier thresholds. Use when reviewing routing statistics or tuning a shared router; recorded success and savings fields are caller claims, not independently verified outcomes.
---

# Control loop — routing telemetry and threshold proposals

This module aggregates routing records and proposes a small change to the LOCAL
threshold. Applying that proposal changes subsequent decisions by
[auto_router](../auto_router/SKILL.md). Consult [effects.json](effects.json) and the
[common contract](../../docs/capability-effects.md) for the selected operation.

```bash
python -m skills.control_loop.cli analyze            # local %, savings, escalation/success
python -m skills.control_loop.cli adapt              # proposed threshold change + why
python -m skills.control_loop.cli adapt --apply      # write it; the router uses it next time
python -m skills.control_loop.cli reset              # back to defaults
```

## Operations and effects

| Operation | Consequence |
|---|---|
| `record` | Best-effort append to `~/.botte/control-ledger.jsonl` or an explicit path. Stores a task excerpt of up to 80 characters, timestamp and caller-supplied routing fields. Repeating it appends again. |
| `load`, `analyze`, `adapt` without `--apply` | Read records/thresholds or use explicit inputs; return aggregates or a proposal. No threshold write. MCP `routing_stats` only analyzes and proposes. |
| `apply`, CLI `adapt --apply` | Validate and atomically replace `~/.botte/routing-thresholds.json` or the supplied destination; CLI writes only if the proposal changed. Future decisions can use the new thresholds immediately. |
| `reset` | Write default thresholds with a new timestamp. This is a mutation, not restoration of an earlier custom configuration or removal of history. |

Thresholds must be four finite JSON numbers satisfying
`0 <= free < local < cheap < standard <= 1`. Booleans, numeric strings, NaN,
infinity and invalid ordering are rejected before creating directories or changing
the destination. The auto-router reader falls back to its defaults for malformed
configuration, without repairing the file. A failed atomic replacement preserves
the preceding file; there is no lock, history archive or compare-and-swap against
another writer. Replacement uses the temporary file's permissions and replaces a
destination symlink rather than following it; check any cross-account readers or
symlink-based setup. Imported validation/writing helpers have their own version scope.

`adapt` needs at least 10 aggregate samples. It raises the LOCAL boundary by 0.03
when reported success is at least 85% and escalation below 15%, or lowers it when
escalation exceeds 30%, with clamps and ordering checks. A step that cannot retain
ordered thresholds is returned as unchanged. These are heuristic proposals.

The ledger is shared by the user account, not automatically separated by project,
model version, runtime or task. AutoRouter records returned calls on its ordinary
success path; cache hits and some failures are absent. Its `success` field reflects
nonempty text, and its saved-token field is not a measured cloud counterfactual.
`analyze` uses aggregate rates, assumes success when that field is absent, and does
not authenticate records or independently establish local-model reliability.
Malformed JSON lines are skipped; structurally invalid records can still prevent
analysis. A high reported rate is therefore not evidence that tasks were correct.

## Recovery and reuse

Before applying a proposal, inspect representative records, independent task
evidence, the affected user account and the current configuration. Existing task
authorization must cover that shared routing change. Reading stats or obtaining a
proposal does not authorize an apply, deployment, training or model activation.
This module does not schedule adaptation or automatically verify learning labels.

Preserve an appropriate prior configuration when rollback matters. After an
interruption inspect the file and any later writer before retrying; a repeat can
append duplicate telemetry or advance a proposed step again. Restore the intended
snapshot only within the task scope. A local rollback cannot undo inference costs,
disclosures or decisions already made under the changed thresholds.

Plausible reuse: evaluate a threshold proposal offline with a target-scoped ledger,
fixed model/configuration versions and independent success labels. Compare the
candidate against the current policy on representative tasks, including failures,
before deciding whether to apply it. Current fixtures prove specific persistence,
validation and read-only proposal behavior, not production improvement or savings.
