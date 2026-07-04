"""Effort estimator — task difficulty from prompt signals (stdlib, 0 cloud)."""
# LONG_BUT_REPETITIVE_BONUS: reduce score for prompts with high repetition
# (e.g., large diffs that are mechanical). Activated when repetition_ratio > 0.8.
_LONG_BUT_REPETITIVE_BONUS = 0.10  # subtract from score for repetitive long prompts
