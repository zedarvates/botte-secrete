"""Composite prompt splitter — route sub-tasks independently.

Splits prompts like "refactor X AND write tests for Y" into independent
sub-tasks, routes each separately, and combines results.

    from skills.auto_router.composite import split_and_route
    results = split_and_route("refactor auth AND write tests for payment")
"""

from __future__ import annotations

import re

SPLITTERS = [
    r"\s+AND\s+",
    r"\s+ET\s+",
    r"\s+puis\s+",
    r"\s+then\s+",
    r"\s+ensuite\s+",
]


def split_prompt(prompt: str) -> list[str]:
    """Detect composite prompts and split into sub-tasks."""
    for sep in SPLITTERS:
        parts = re.split(sep, prompt, flags=re.IGNORECASE)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
    return [prompt]


def split_and_route(prompt: str, task_type: str = "") -> list[dict]:
    """Split composite prompt and route each sub-task independently."""
    from skills.auto_router import auto_route

    sub_tasks = split_prompt(prompt)
    results = []
    for task in sub_tasks:
        decision = auto_route(task, task_type)
        results.append({"task": task, "decision": decision})
    return results
