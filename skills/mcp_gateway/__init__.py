"""mcp_gateway — Botte Secrète MCP Gateway.

    # En tant que serveur (stdio)
    python -m skills.mcp_gateway.server

    # En tant que CLI
    python -m skills.mcp_gateway.cli list
    python -m skills.mcp_gateway.cli call security_scanner '{"root": "."}'
"""

from skills.mcp_gateway.server import MCPServer, serve_stdio
from skills.mcp_gateway.registry import discover_skills, SkillTool
from skills.mcp_gateway.dispatcher import Dispatcher

__all__ = [
    "MCPServer", "serve_stdio",
    "discover_skills", "SkillTool",
    "Dispatcher",
]
