---
name: safe_exit
layer: VERIFY
description: Deterministic bounded-execution guard for agent loops. Use to stop iteration, tool-call, wall-time, repeated-failure, or no-progress loops and to enforce non-escalating authorization plus snapshot gates for destructive actions.
tags: [safety, agent, loop, budget, supervisor, validation]
triggers: [safe exit, agent loop, stagnation, destructive action, authorization tier]
---

# SAFE-EXIT — bounded agent execution

SAFE-EXIT is a deterministic guard; it is not an LLM and does not execute tools.
It records run progress and returns `UNCERTAIN` when a configured budget is
exhausted or the trajectory stagnates.

## Run guard

```python
from skills.safe_exit import SafeExitConfig, SafeExitGuard

guard = SafeExitGuard(SafeExitConfig(max_iterations=12, max_tool_calls=48))
result = guard.observe(score=0.72, tool_calls_delta=3)
if result.decision.value == "UNCERTAIN":
    # stop the current trajectory; supervisor may choose a different plan/model
    ...
```

Supported stop reasons:

- `iteration_budget_exhausted`
- `tool_budget_exhausted`
- `wall_time_budget_exhausted`
- `repeated_equivalent_failure`
- `no_score_progress`

A caller may start a new trajectory with a new plan/model after SAFE-EXIT, but
must not silently reset the budget inside the same run.

## Authorization gate

```python
from skills.safe_exit import ActionIntent, AuthorizationTier, validate_action

intent = ActionIntent(
    "remove generated worktree",
    requested_tier=AuthorizationTier.ACT,
    destructive=True,
    snapshot_id="git:abc123",
)
decision = validate_action(intent, current_tier=AuthorizationTier.ACT)
```

Rules:

- `SIMULATE < SHADOW < ACT`;
- an action cannot request a higher tier than the current run;
- destructive actions require `ACT`;
- destructive actions require a non-empty recoverable snapshot identifier;
- a successful benchmark never promotes an agent to a higher tier by itself.

## Integration boundary

SAFE-EXIT should wrap, not replace, the existing Gauntlet/harness. The caller is
responsible for persisting `RunGuardResult` and `ActionDecision` into the run
manifest and for actually stopping the loop when `UNCERTAIN` is returned.

Network isolation remains an OS/container/tool-plane responsibility. SAFE-EXIT
must not be used as a substitute for network policy or sandboxing.
