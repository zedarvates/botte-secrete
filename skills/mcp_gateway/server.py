"""server — MCP server over stdio (JSON-RPC 2.0, stdlib only).

Exposes Botte skills as MCP tools. Protocol:
    → {"jsonrpc":"2.0","id":1,"method":"tools/list"}
    ← {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

    → {"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"security_scanner","arguments":{"root":"."}}}
    ← {"jsonrpc":"2.0","id":2,"result":{"content":[...]}}

Compatible with Claude Code, Codex, Cursor, and any MCP client.

Register in .mcp.json:
{
    "mcpServers": {
        "botte-gateway": {
            "command": "python",
            "args": ["-m", "skills.mcp_gateway.server"],
            "cwd": "/path/to/botte-secrete"
        }
    }
}
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.mcp_gateway.registry import discover_skills, load_config, SkillTool
from skills.mcp_gateway.dispatcher import Dispatcher

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "botte-gateway", "version": "1.0.0"}


def _build_tool_definitions(skills: list[SkillTool]) -> list[dict]:
    """Build MCP tool definitions from discovered skills.

    Each tool gets an inputSchema based on the skill's expected arguments.
    """
    tools = []
    for skill in skills:
        if not skill.enabled:
            continue

        # Build input schema
        properties: dict = {}
        required: list[str] = []

        if skill.name == "security_scanner":
            properties["root"] = {"type": "string", "description": "Path to scan"}
            properties["fail_on"] = {"type": "string", "enum": ["critical", "error", "warning", "info"],
                                      "description": "Minimum severity to fail on"}
            required.append("root")
        elif skill.name == "fast_context":
            properties["root"] = {"type": "string", "description": "Project root"}
            properties["query"] = {"type": "string", "description": "What to look for"}
            required.extend(["root", "query"])
        elif skill.name == "meta_harness":
            properties["workdir"] = {"type": "string", "description": "Project root"}
            properties["agents"] = {"type": "array", "items": {"type": "string"},
                                     "description": "Agent names or plan name"}
            properties["approval"] = {"type": "boolean", "description": "Require human approval"}
            required.extend(["workdir", "agents"])
        elif skill.name == "botte_nn":
            properties["model"] = {"type": "string", "enum": ["effort_classifier", "binary_router", "anomaly_detector"],
                                    "description": "Model to use"}
            properties["input"] = {"type": "array", "items": {"type": "number"},
                                    "description": "Input features"}
            required.extend(["model", "input"])
        else:
            # Generic: root path
            properties["target"] = {"type": "string", "description": "Target path"}
            required.append("target")

        tools.append({
            "name": skill.name,
            "description": skill.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        })

    return tools


class MCPServer:
    """MCP server that exposes Botte skills via stdio JSON-RPC."""

    def __init__(self):
        self.skills = discover_skills()
        self.config = load_config()
        self.dispatcher = Dispatcher()

        # Apply config filters
        if self.config.get("enabled_skills"):
            for s in self.skills:
                if s.name not in self.config["enabled_skills"]:
                    s.enabled = False
        for excl in self.config.get("excluded_skills", []):
            for s in self.skills:
                if s.name == excl:
                    s.enabled = False

        self.tools = _build_tool_definitions(self.skills)

    def handle(self, request: dict) -> Optional[dict]:
        """Handle a single JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"tools": self.tools},
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            # Find the tool
            tool = next((t for t in self.skills if t.name == tool_name), None)
            if not tool:
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"},
                }

            result = self.dispatcher.call(tool, arguments)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": result,
            }

        elif method == "notifications/initialized":
            return None  # No response for notifications

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        else:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }


def serve_stdio():
    """Serve MCP requests over stdin/stdout (JSON-RPC 2.0)."""
    server = MCPServer()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        try:
            response = server.handle(request)
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {e}"},
            }

        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve_stdio()
