# Kanboard quality-status consumption

Kanboard Neo, Odin, or another authenticated task plane can read one passive
Quality Compass observation without receiving task text or private fingerprints:

```bash
botte qa task-status --project /path/to/project \
  --task-ref kanboard:task:76 --json
```

The same contract is available through MCP tool `qa_task_status`. Its output is
`botte.task-quality-status/v1`.

## Consumer rules

1. Treat `task_ref` only as the caller-supplied opaque correlation key.
2. Display `state`, `reason_code`, and `next_safe_action` as an observation.
3. Store only `outcome_id` and `evidence_refs`; fetch evidence through the
   authenticated system that owns each reference. The packet contains no
   evidence body.
4. Never interpret `suggested_task_state` as permission to mutate a task.
   `task_transition_allowed` and `terminal` are always false.
5. Require a person or the task plane's existing policy gate before moving a
   card, closing work, retrying, deploying, or training.
6. Ignore evidence references unless `verified` is true. Botte already removes
   references from rejected and unverified observations.

Every outcome suggests Kanboard's existing `review` state, never `done`. The
packet's own `state` still distinguishes a verified failure from uncertainty,
abstention, escalation, or success. Do not map this packet into Kanboard's
training-eligible quality-evaluation endpoint: it is a status observation, not
a new independent review. Approval-required and escalated outcomes remain
human-gated. Replaying the same task reference and outcome produces the same
packet ID.

The private `botte.quality-outcome/v1` ledger remains the source of truth. Do
not copy it wholesale into Kanboard, public snapshots, logs, or notifications.
