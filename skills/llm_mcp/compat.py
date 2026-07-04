"""MCP server compatibility contract — versioning for tool names.

Botte MCP tools follow semver-like naming: `tool_name_v1`, `tool_name_v2`.
When a breaking change is needed, add a new version; keep the old one for
one release cycle. Clients should specify the version they expect.

See docs/schemas/mcp-compatibility.md for the full contract.
"""

# Current tool versions (bump on breaking changes)
TOOL_VERSIONS = {
    "route_task": 1,
    "local_chat": 1,
    "bench_run": 1,
    "doctor": 1,
    "fleet_status": 1,
    "context_profiler": 1,
}


def resolve_tool(name: str, version: int = 1) -> str:
    """Resolve a tool name with version. Returns the handler name."""
    ver = TOOL_VERSIONS.get(name, 1)
    if version > ver:
        raise ValueError(f"Tool {name} v{version} not available (latest: v{ver})")
    return f"{name}_v{ver}"
