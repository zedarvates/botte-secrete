"""Hermes bridge response size limit — protects against oversized payloads.

Some frameworks (Cursor, Windsurf) have payload limits. This module enforces
a configurable max response size for hermes_bridge.dispatch().
"""

MAX_RESPONSE_BYTES = 100_000  # default: 100 KB


def enforce_limit(response: dict, max_bytes: int = MAX_RESPONSE_BYTES) -> dict:
    """Truncate response if it exceeds the size limit. Returns the (maybe truncated) dict."""
    import json
    raw = json.dumps(response, default=str)
    if len(raw) <= max_bytes:
        return response
    # Truncate: keep structure, drop long fields
    for key in ("text", "answer", "content", "output"):
        if key in response and isinstance(response[key], str):
            available = max_bytes - len(json.dumps({k: v for k, v in response.items() if k != key}, default=str))
            if available > 200:
                response[key] = response[key][:available] + "...[truncated]"
                break
    return response
