---
name: control_loop
layer: GOVERN
description: Close the system into a self-improving loop — measure routing outcomes (local %, token savings, escalation/success rates) and adapt the effort→tier thresholds the auto-router reads, so it gets better at keeping work local without failing. Use to see routing stats, tune the router from real outcomes, or reset thresholds. Also use when the user wants the system to adapt/learn its routing automatically.
---

# control_loop — the router that learns

The final systemic loop: every routing decision + outcome is recorded, and the
effort→tier thresholds (read live by [[auto_router]]) are nudged from the data —
keep more work local when local is reliable, escalate sooner when it isn't.

```bash
python -m skills.control_loop.cli analyze            # local %, savings, escalation/success
python -m skills.control_loop.cli adapt              # proposed threshold change + why
python -m skills.control_loop.cli adapt --apply      # write it; the router uses it next time
python -m skills.control_loop.cli reset              # back to defaults
```

## How the loop closes

1. **Measure** — `auto_router.run` records each call to `~/.botte/control-ledger.jsonl`
   (effort, tier, local/cloud, tokens saved, escalated, success).
2. **Analyze** — aggregate: local %, escalation rate, success rate, tokens saved.
3. **Adapt** — conservative rule, needs ≥10 samples, small steps, clamped:
   - local reliable (success ≥85%, escalation <15%) → **raise** the LOCAL boundary
     (keep more work local → more savings).
   - local insufficient (escalation >30%) → **lower** it (escalate borderline sooner).
4. **Apply** — write `~/.botte/routing-thresholds.json`; `auto_router.effort` reads
   it live, so the next decisions reflect what actually worked.

This is the Karpathy/second-brain pattern applied to routing: the system gets
smarter from its own outcomes. Exposed via [[llm_mcp]] as `routing_stats`.
Related: [[auto_router]], [[conductor]], [[metrics]].
