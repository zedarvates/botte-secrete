"""context_profiler — measure the always-on prefix vs a small model's window.

    from skills.context_profiler import profile
    profile(".")   # prefix tokens (directives + tools + skills) + % of 64k/128k/256k
"""

from skills.context_profiler.profiler import profile, summarize, DEFAULT_WINDOWS

__all__ = ["profile", "summarize", "DEFAULT_WINDOWS"]
