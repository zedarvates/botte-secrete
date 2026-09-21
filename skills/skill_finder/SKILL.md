---
name: skill_finder
description: Retrieve candidate skills from local SKILL.md files, with optional local-model review of their complete bodies. Use for skill discovery or narrowing a tool shortlist. Results are advisory; choosing an operation also requires checking its instructions, exclusions and task prerequisites.
---

# skill_finder — local, zero-token skill & tool search

Search produces candidates locally. Confirm applicability against the actual
operation and task before execution; a lexical score does not establish fit.

## Two tiers

- **Tier 0 — free (0 tokens total):** lexical + fuzzy match over each skill's
  name, description, tags, triggers and full SKILL.md body. Deterministic.
- **Tier 1 — local (0 cloud tokens):** a local model (via [[llm_backends]])
  reviews complete shortlisted `SKILL.md` bodies, can retain a subset in its
  preferred order or explicitly abstain. Local inference costs remain unmeasured.

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

## Review and handoff

Use the returned paths as identities; equal names can refer to different skills.
Read the selected instructions completely and inspect relevant referenced
resources. Check suitable uses, exclusions and prerequisites for the requested
operation. The local reviewer receives full bodies, but referenced files and
live environment checks remain the task agent's responsibility.

With `--local`, `local_review.status` is `selected`, `abstained` or `unavailable`.
Selected results contain only the retained candidates; an explicit `0` response
leaves no matches. Unavailable or malformed review preserves the lexical
shortlist and gives a reason; it is not a positive applicability verdict.
The reviewer reads at most 64 KiB of instruction bytes across the shortlist.
Missing, invalid UTF-8, empty or over-budget instructions prevent the model call;
no truncated document is presented as complete. Reduce the shortlist or review
the full documents directly when this limit applies.

`local_review.instruction_sha256` binds the bodies actually read. Recheck sources
before reuse: these hashes neither attest model understanding nor verify task
success. Remembered advice must retain its context and uncertainty. No skill
command, referenced file, memory write or deployment is triggered by the review.
The Python `local_rerank` helper retains its legacy name output; use
`include_paths=True` for unambiguous identities, with `[]` for abstention and
`None` for unavailable review.

See [selection review evaluation](../../docs/skill-selection-review.md) for the
replay checks, source binding and limits of the measured evidence.

Exposed via [[llm_mcp]] as the `find_skills` tool. Related:
`skill_project_optimizer` (rule-based per-project filtering), `auto_router`.
