---
name: skill_finder
description: Rank skills locally by lexical and fuzzy matching over SKILL.md metadata and bodies. Optional reranking uses a configured local model. Use to shortlist relevant tools; returned paths and truncated descriptions are discovery hints, not verified capabilities, permission to execute or measured host-agent token savings.
---

# skill_finder — local skill search

## Two tiers

- **Tier 0:** deterministic lexical and fuzzy matching over name, description,
  tags, triggers and full SKILL.md body. The search routine does not call an LLM.
- **Tier 1:** optional reranking with a configured local model through
  [[llm_backends]]. Local inference consumes model tokens and compute. If no
  suitable backend or result is available, the lexical order is retained.

```bash
python -m skills.skill_finder.cli "optimize slow postgres queries"
python -m skills.skill_finder.cli "set up an A/B test" --local
python -m skills.skill_finder.cli "audit dead code" --roots ~/.claude/skills --json
```

```python
from skills.skill_finder import find

result = find("decide local vs cloud routing", top_k=5)
# matches contain name, score, why, description, path and tokens_est.
```

`--roots` selects trees containing `SKILL.md` files; the default is the runtime
package's `skills/` directory. Bodies are indexed with or without frontmatter.
Returned descriptions are truncated to 160 characters. The full instructions
are not loaded into a host agent automatically: read the selected reference and
check the tool schema, prerequisites and evidence before use.

The result's `cloud_tokens: 0` is an implementation marker for this local search,
not a provider usage measurement. An agent invoking the tool or interpreting
its shortlist may still consume model tokens. Shortlisting can reduce supplied
context, but savings and selection quality require measurement on actual tasks.

Exposed through [[llm_mcp]] as `find_skills`. Related modules:
[[skill_project_optimizer]] and [[auto_router]].
