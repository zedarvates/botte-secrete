"""
Pre-code hook for workflow-check — enforce decision ladder before implementation.

Add to workflow-check's SKILL.md or call directly:
    from skills.decision_ladder.hook import pre_code_check
    result = pre_code_check("add email validation to user model")
    if result.rung != "new_code":
        print(f"⚠️ No new code needed — use {result.rung}: {result.solution}")
"""

from skills.decision_ladder.ladder import climb, LadderResult


def pre_code_check(task: str, strict: bool = False) -> LadderResult:
    """Check if new code is actually needed for this task.

    Args:
        task: The task description
        strict: If True, raise an error when code could be avoided.
                If False (default), return the result as a warning.

    Returns:
        LadderResult with the suggested approach
    """
    result = climb(task)
    if result.rung != "new_code" and strict:
        raise ValueError(
            f"Decision ladder says NO: {result.rung} handles this. "
            f"Use {result.solution} instead of writing new code. "
            f"Estimated {result.saved_lines} lines saved."
        )
    return result


def should_write_code(task: str) -> bool:
    """Quick check: does this task genuinely need new code?"""
    return climb(task).rung == "new_code"


def format_warning(result: LadderResult) -> str:
    """Format a human-readable warning."""
    if result.rung == "new_code":
        return f"✅ {result.task[:50]} — new code is justified"
    return (
        f"⚠️ {result.task[:50]} → use {result.rung} instead\n"
        f"   Solution: {result.solution}\n"
        f"   Saved: ~{result.saved_lines} lines (confidence: {result.confidence:.0%})"
    )
