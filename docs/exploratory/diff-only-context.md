# Diff-only context — agent optimization idea

Instead of returning the full file after every edit, return only the diff applied.
This reduces context tokens for iterative coding sessions where the agent makes
many small edits to large files.

## Current state
- `patch` tool already returns unified diffs
- `write_file` returns the full content (costly for large files)

## Implementation sketch
```python
# In the tool response, prefer diffs over full content
if edit_tool_used and file_size > 1000:
    return diff_only  # save ~80% context tokens
```

## Self-audit periodic
Extension of `docs_steward`: the project audits its own convention drift over time.
- Track SKILL.md drift (stale references, outdated commands)
- Track AGENTS.md staleness
- Version results via `trends.snapshot`
- Alert when drift exceeds threshold

Run via cron: `python -m skills.docs_steward --auto-audit`
