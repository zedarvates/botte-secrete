---
name: metrics
description: Cost-focused project metrics, broken down per component — LOC by language and component, duplicate-function groups, directive health, always-on context cost (CLAUDE.md tokens × turns), local-routing posture, skill-search tokens avoided, and the audit's own (near-zero) cost. Use when the user wants to quantify a project's token/cost profile, see LOC/health per component, or measure what the toolkit saves.
---

# metrics — quantify a project's token/cost profile

Surfaces the numbers an audit should give you, framed around cost. A multi-stack
project (website + game server + client + tools) has **no single number**, so
everything is broken down per component.

```bash
python -m skills.metrics.cli <project>
python -m skills.metrics.cli <project> --porthos reports/<proj>/audit-report.json --json
```

## What it reports

- **LOC** by language and by top-level **component** (with bars).
- **Duplicate-function groups** (stdlib AST, free).
- **Directive health** + **always-on context cost**: instruction tokens × turns
  — e.g. a 2.3k-token CLAUDE.md ≈ **70k tokens/session** just re-sending rules.
- **Local-routing posture**: backends present → cheap work at 0 cloud tokens.
- **Skill-search tokens avoided** by `find_skills` (catalog × ~150 tok).
- **The audit's own cost**: `analysis_llm_tokens = 0` — the scans are
  deterministic Python; only synthesis by the orchestrating model costs tokens.
- **Deep audit** summary (health / dead code / secrets) if a Porthos
  `audit-report.json` is reachable (`.botte/` or `--porthos`).

## Why this framing

The headline an audit should produce: *"analysis cost 0 tokens; your always-on
instructions cost ~70k/session; local routing can move cheap work to 0 cloud
tokens."* That's the number that justifies the toolkit.

Exposed via [[llm_mcp]] as the `metrics` tool. Related: [[infra_advisor]]
(auto audit), [[directives_audit]], [[skill_finder]], [[bootstrap]].
