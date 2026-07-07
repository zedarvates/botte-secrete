"""Hermes Bridge — connects Hermes Agent to botte-secrete tools."""
from skills.hermes_bridge.bridge import TOOL_SCHEMAS, dispatch, mcp_config
from skills.hermes_bridge.registry import SkillRegistry, get_registry, init_registry
from skills.hermes_bridge.mcp_server import MCP_TOOLS, handle_request

__all__ = [
    "TOOL_SCHEMAS", "dispatch", "mcp_config",
    "SkillRegistry", "get_registry", "init_registry",
    "MCP_TOOLS", "handle_request",
]
