"""context_profiler — measure the always-on prefix vs a small model's window.

    from skills.context_profiler import profile, profile_host
    profile(".")       # prefix tokens (directives + tools + skills) + % of 64k/128k/256k
    profile_host(".")  # same + host-level estimation (system, memory, host skills, MCP)
"""

from skills.context_profiler.profiler import profile, profile_host, summarize, DEFAULT_WINDOWS

__all__ = ["profile", "profile_host", "summarize", "DEFAULT_WINDOWS"]
