# Karpathy Guidelines — LLM Anti-Patterns for Coding

> Adapted from [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)

## The 4 Principles

### P1 — Think Before Coding

**Rule:** Don't code until the problem is understood. Plan first.

✅ Good:
- "I understand the problem: need to parse 3 formats. I'll write a plan."
- "I see 2 possible approaches. Which do you prefer?"

❌ Bad:
- "I'll write the code and see if it works" (trial-and-error in production)
- Adding 500 lines without explaining the logic

**Checklist:**
- [ ] Did I understand the problem before writing code?
- [ ] Did I explore alternatives before choosing an approach?
- [ ] Is the plan documented (even 2 lines)?

### P2 — Simplicity

**Rule:** The simplest solution is the best. No premature abstractions.

✅ Good:
- A 20-line function that does one thing clearly
- Simple `if/else` rather than obscure pattern matching
- "We'll see if we need an abstraction later"

❌ Bad:
- `AbstractDataExporterFactory` for exporting 2 formats
- "Extensible" architecture for cases that don't exist yet
- Strategy pattern for 2 simple behaviors

**Checklist:**
- [ ] Can I delete 30% of the code without losing functionality?
- [ ] Is this abstraction necessary NOW?
- [ ] Would a new contributor understand this code in 30s?

### P3 — Clean Diffs

**Rule:** Never mix formatting and logic in the same diff.

✅ Good:
- One commit that reformats code
- A separate commit that changes logic
- Rename in one commit, modify in another

❌ Bad:
- `git diff` with 300 lines of formatting + 2 lines of logic
- Changing indentation AND logic in the same commit

**Checklist:**
- [ ] Are formatting changes in a separate commit?
- [ ] Are deleted comments truly obsolete?
- [ ] Are renames isolated from logic changes?

### P4 — Verifiable Tests

**Rule:** Don't trust the LLM — always verify with tests.

✅ Good:
- Test with real inputs (not perfect mocks)
- Success criterion: "test X passes" not "looks like it works"
- Test that reproduces the bug before fixing it

❌ Bad:
- "The code looks correct" (self-preference)
- Agent judges itself (same context = biased)
- No test = no proof

**Checklist:**
- [ ] Is there a test that verifies the expected behavior?
- [ ] Does the test pass BEFORE the change (regression)?
- [ ] Is the success criterion VERIFIABLE?

## Common Anti-Patterns

| Anti-pattern | Problem | Solution |
|-------------|---------|----------|
| Trial-and-error | Wastes time, accumulates dead code | Plan first (P1) |
| Feature creep | Code that does too much | Delete 30% (P2) |
| Format+logic mix | Unreadable diffs, conflicts | Separate commits (P3) |
| Self-review | Agent judges itself biased | Separate agent (P4) |
| Magic numbers | Unnamed constants | Name constants |
| Deep nesting | if inside if inside if | Early return, guard clauses |
| Copy-paste | Duplication instead of factorization | Extract function |
