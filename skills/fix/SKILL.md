---
name: fix
layer: ACT
description: List a project's correctable issues — confirmed dead code, duplication, stale directive references — each with a tokens·model·money·time cost estimate and a total. Plan-only by design (never edits code automatically). Use when the user asks what's worth fixing and what each fix costs.
---

# fix — correctable issues, each with its cost

```bash
python -m skills.fix.cli .            # plan + per-kind cost + total
python -m skills.fix.cli . --save md  # timestamped report
```

Enumerates genuine fixes (dead code ≥0.85 confidence, duplication, stale CLAUDE.md
/AGENTS.md refs) and attaches **tokens · model · money · time** to each via
[[cost_estimator]], plus a grand total. **Plan-only** — it never edits files
(auto-fixers have broken this repo before); apply with review. Exposed via
[[llm_mcp]] as `fix_plan`. Related: [[cost_estimator]], [[fallow_like]], [[checkup]].
