#!/usr/bin/env python3
"""MCP server --dry-run mode — log tool calls without executing.

    python -m skills.llm_mcp.server --dry-run

Useful for auditing untrusted MCP clients before authorizing in production.
"""

# Dry-run mode: when enabled, all tool calls are logged to stderr but not executed.
# Set via environment variable: BOTTE_MCP_DRY_RUN=1
DRY_RUN = False


def enable_dry_run():
    global DRY_RUN
    DRY_RUN = True


def dry_run_log(tool_name: str, params: dict) -> None:
    """Log a tool call in dry-run mode."""
    import json, sys
    print(json.dumps({
        "dry_run": True,
        "tool": tool_name,
        "params": params,
    }), file=sys.stderr)
