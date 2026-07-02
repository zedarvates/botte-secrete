"""The reproducible benchmark corpus — a fixed, versioned set of representative
tasks spanning the effort spectrum (trivial rename → hard system design), so
`bench` measures the same thing every run and the numbers are comparable
across commits. Deliberately NOT the demo scenario (that's for show; this is
for measurement) — but both draw from the same intuition: real prompt shapes
the belt actually sees.
"""

from __future__ import annotations

# (prompt, task_type) — task_type feeds skills.tiered_router.TASK_TIER as a seed.
BENCH_TASKS: list[tuple[str, str]] = [
    # trivial — filter 1/2 territory (micro-NN / deterministic)
    ('rename variable "a" to "count" in utils.py', "simple_qa"),
    ("classify: is this a bug or a feature request?", "simple_qa"),
    ("extract all email addresses from this text", "simple_qa"),
    ("format this JSON with 2-space indent", "simple_qa"),
    ("translate 'hello world' to French", "simple_qa"),
    ("list the files changed in this diff", "simple_qa"),
    # light — short summaries, small refactors
    ("summarize this PR in 2 lines", "doc_generate"),
    ("suggest a better name for this function", "refactor_suggest"),
    ("write a docstring for this function", "doc_generate"),
    ("fix this off-by-one error in the loop", "simple_qa"),
    # moderate — code review, medium refactor
    ("review this diff for obvious bugs", "code_review"),
    ("refactor this function to remove duplication", "refactor_suggest"),
    ("write unit tests for this parser", "code_review"),
    # hard — reasoning, design, security
    ("design a distributed consensus protocol with a correctness proof", "system_design"),
    ("audit this auth flow for a race condition and propose a fix", "critical_fix"),
    ("debug this deadlock from the stack trace and explain root cause", "critical_fix"),
    ("design the caching layer for a multi-region service, discuss trade-offs", "system_design"),
]
