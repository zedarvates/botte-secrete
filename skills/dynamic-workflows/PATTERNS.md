# Dynamic Workflows — 6 Patterns for Efficient Agents

> Inspired by Mark Kashef & Anthropic "A Harness for Every Task"

## The 3 Problems Solved

| Problem | Symptom | Solution |
|---------|---------|----------|
| Agent Laziness | Says 15 tasks, does 7 | Separate sub-agents, clean context |
| Self-Preference | Judges own work → biased | Adversarial skeptics (fresh context) |
| Goal Drift | Loses goal in long sessions | DAG context + verifiable criteria |

## Pattern 1: Classify and Act

**Concept:** Receptionist agent → classifies → routes to specialist.

```
Input → Classifier → [Category A → Agent A]
                     [Category B → Agent B]
                     [Other → Agent Default]
```

**Use for:** Ticket triage, email routing, request classification.

## Pattern 2: Fan Out and Synthesize

**Concept:** Split into mutually exclusive sub-tasks → parallel → synthesize.

```
Task → [Angle 1] → \
      [Angle 2] → → Synthesizer → Result
      [Angle 3] → /
```

**Use for:** Research, due diligence, multi-perspective analysis.

## Pattern 3: Adversarial Verification

**Concept:** 3+ skeptics with different roles verify work against a rubric.

```
Work → [Skeptic 1: Logic] → \
        [Skeptic 2: Facts] → → Report
        [Skeptic 3: Bias] → /
```

**Use for:** Fact-checking, code review, bias detection.

## Pattern 4: Generate and Filter

**Concept:** Over-generate (1000 > 10) → separate judges → filter.

```
Generator → [1000 options] → Judge → Top 10
```

**Use for:** Brainstorming, design selection, A/B testing.

## Pattern 5: Tournament

**Concept:** Pairwise comparisons → bracket → each match = fresh agent.

```
Round 1: [A vs B] [C vs D] [E vs F]
Round 2: [Winner1 vs Winner2] [Winner3 vs Bye]
Final: [Winner vs Winner]
```

**Use for:** Ranking candidates, prioritization, complex decisions.

## Pattern 6: Loop Until Done

**Concept:** Loop until verifiable criterion (no fixed count).

```
Iteration 1 → Test → Fail → Iteration 2 → Test → Pass → Done
                              ↑                  ↓
                         Max N iterations    Verified result
```

**Use for:** Debug flaky, iterative optimization, exhaustive search.

## Design Checklist

- [ ] Pattern matches the problem?
- [ ] AND/OR/XOR conditions explicit?
- [ ] "Other" category present (inclusive OR)?
- [ ] Isolated contexts between agents?
- [ ] Verifiable success criteria?
- [ ] Safety net (max iterations, timeout)?
- [ ] Traceability ensured?
- [ ] Creator XOR Verifier?
