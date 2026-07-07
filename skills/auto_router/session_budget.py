"""Budget de session configurable — bloque les appels cloud quand dépassé.

Configurable via .botte/policy.md:
    _SESSION_LIMIT = 25000   # max cloud tokens this session
"""

SESSION_LIMIT_KEY = "_SESSION_LIMIT"


def load_session_limit(project: str = ".") -> int:
    """Load session token limit from project policy, default 50000."""
    try:
        from skills.preflight.policy import load
        import re
        policy = load(project)
        m = re.search(rf"{SESSION_LIMIT_KEY}\s*=\s*(\d+)", policy)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 50000
