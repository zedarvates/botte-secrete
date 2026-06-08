# Simplify Code — Parallel 3-Agent Review

> Three narrow reviewers beat one broad reviewer.

## When to Use

- "simplify" / "simplify my changes" / "review my code"
- "review my recent changes" / "clean up my changes"

## The Process

### Phase 1 — Identify Changes

```bash
# Default: uncommitted working-tree changes
git diff

# If empty, include staged
git diff HEAD

# Scoped variants
git diff --staged          # staged changes
git diff HEAD~1            # last commit
git diff main...HEAD       # this branch / PR
git diff -- src/foo.py     # specific file(s)
```

### Phase 2 — Launch 3 Reviewers in Parallel

Use `delegate_task` batch mode with 3 concurrent tasks:

**Reviewer 1 — Code Reuse**
> Review this diff for code that duplicates existing functionality.
> Search for existing functions, constants, or patterns the new code
> could call instead of reimplementing.

**Reviewer 2 — Code Quality**
> Review this diff for quality problems: redundant state, parameter
> sprawl, copy-paste-with-variation, leaky abstractions, stringly-typed code.

**Reviewer 3 — Efficiency**
> Review this diff for efficiency problems: unnecessary work, missed
> concurrency, hot-path bloat, TOCTOU anti-patterns, memory issues.

### Phase 3 — Aggregate and Apply

1. Merge findings, deduping overlaps
2. Discard false positives
3. Resolve conflicts (correctness > focus > readability > micro-perf)
4. Apply fixes with `patch` / `write_file`
5. Verify: run targeted tests + linter
6. Summarize what changed

## Pitfalls

- Don't fan out wider than 3
- Give the WHOLE diff to each reviewer
- Reviewers search, they don't guess — require `file:line` evidence
- Apply ≠ rewrite — keep edits scoped to the diff
- Respect project conventions
