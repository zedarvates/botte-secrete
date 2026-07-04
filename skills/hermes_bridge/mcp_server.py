"""
Hermes Bridge MCP Server — connects Hermes Agent to botte-secrete tools.

Exposes botte-secrete skills as MCP tools that Hermes can call.

Usage:
    python -m skills.hermes_bridge.mcp_server
    # Then configure Hermes to use this MCP server
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.decision_ladder.ladder import climb
from skills.universal_compressor.compressor import compress
from skills.auto_memory.hook import memory_stats
from skills.dashboard.api import load_metrics


MCP_TOOLS = {
    "decision_ladder": {
        "description": "Check if new code is needed using Ponytail YAGNI ladder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task description to evaluate"},
            },
            "required": ["task"],
        },
    },
    "compress_content": {
        "description": "Compress content to reduce token usage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to compress"},
                "content_type": {"type": "string", "enum": ["auto", "text", "json", "log", "tool_output", "code"], "default": "auto"},
            },
            "required": ["content"],
        },
    },
    "memory_stats": {
        "description": "Get current memory bank statistics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "dashboard_stats": {
        "description": "Get dashboard metrics (tests, lines saved, rungs).",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [{"name": k, **v} for k, v in MCP_TOOLS.items()]},
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if tool_name == "decision_ladder":
            result = climb(args.get("task", ""))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({
                        "rung": result.rung,
                        "solution": result.solution,
                        "saved_lines": result.saved_lines,
                        "confidence": result.confidence,
                    })}]
                },
            }

        if tool_name == "compress_content":
            result = compress(args.get("content", ""), args.get("content_type", "auto"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({
                        "data": result.data[:200] + ("..." if len(result.data) > 200 else ""),
                        "original_size": result.original_size,
                        "compressed_size": result.compressed_size,
                        "ratio": result.ratio,
                        "strategy": result.strategy,
                    })}]
                },
            }

        if tool_name == "memory_stats":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(memory_stats())}]
                },
            }

        if tool_name == "dashboard_stats":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(load_metrics())}]
                },
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()