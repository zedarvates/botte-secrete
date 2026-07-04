"""Hermes bridge response size limit — protects against oversized payloads.

Some frameworks (Cursor, Windsurf) have payload limits. This module enforces
a configurable max response size for hermes_bridge.dispatch().
"""

MAX_RESPONSE_BYTES = 100_000  # default: 100 KB


def enforce_limit(response: dict, max_bytes: int = MAX_RESPONSE_BYTES) -> dict:
    """Truncate response if it exceeds the size limit. Returns the (maybe truncated) dict."""
    import json
    suffix = "...[truncated]"
    raw = json.dumps(response, default=str, ensure_ascii=False)
    if len(raw) <= max_bytes:
        return response

    # Find the largest text field and truncate it
    best_key = None
    for key in ("text", "answer", "content", "output"):
        if key in response and isinstance(response[key], str):
            best_key = key
            break
    if not best_key:
        return response  # nothing we can truncate

    # Iteratively trim until within budget (max 10 iterations)
    for _ in range(10):
        raw = json.dumps(response, default=str, ensure_ascii=False)
        if len(raw) <= max_bytes:
            return response
        excess = len(raw) - max_bytes + 32  # safety margin
        if excess > 0 and len(response[best_key]) > excess:
            response[best_key] = response[best_key][:max(0, len(response[best_key]) - excess)] + suffix

    return response
