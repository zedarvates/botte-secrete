---
name: skill_finder
description: Find which skills/tools/MCP are relevant to a task by searching SKILL.md files locally — zero cloud tokens (lexical/fuzzy match, optional local-LLM rerank). Use when you need to pick tools for a project or task and want to avoid spending a paid cloud model on the search step. Also use when the user mentions skill search, tool selection, "which skill should I use", or cutting token cost on routing/recall.
---

# skill_finder — local, zero-token skill & tool search

Picking the right skill/tool for a task is **retrieval, not reasoning** — so it
should not cost paid cloud tokens. This module does the search locally and leaves
the cloud model free for the actual work.

## Two tiers

- **Tier 0 — free (0 tokens total):** lexical + fuzzy match over each skill's
  name, description, tags, triggers and full SKILL.md body. Deterministic.
- **Tier 1 — local (0 cloud tokens):** for ambiguous queries, a local model
  (via [[llm_backends]]) re-ranks the shortlist. Still no cloud spend.

## Use it

```bash
python -m skills.skill_finder.cli "optimize slow postgres queries"
python -m skills.skill_finder.cli "set up an A/B test" --local      # local-LLM rerank
python -m skills.skill_finder.cli "audit dead code" --roots ~/.claude/skills --json
```

```python
from skills.skill_finder import find
r = find("decide local vs cloud routing", top_k=5)
r["cloud_tokens"]   # 0
r["matches"]        # [{name, score, why, description, path, tokens_est}, …]
```

`--roots` points at any directory tree containing `SKILL.md` files (your global
skill library, a project's skills, etc.); defaults to this repo's `skills/`.
Works whether or not a SKILL.md has YAML frontmatter — the body is always indexed.

## Why it saves money

A coding agent normally burns expensive context having the cloud model read every
skill description to decide what to load. `find_skills` returns a ranked shortlist
for **0 cloud tokens**, so the cloud model only sees the few skills that matter —
or none, when the local rerank is decisive.

Exposed via [[llm_mcp]] as the `find_skills` tool. Related:
`skill_project_optimizer` (rule-based per-project filtering), `auto_router`.
