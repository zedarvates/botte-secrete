"""
MCP server for Universal Compressor — exposes compress/restore/stats as MCP tools.

Compatible with Claude Code, Cursor, Hermes Agent via stdio JSON-RPC.

Usage:
    python -m skills.universal_compressor.mcp_server
"""

from __future__ import annotations

import json
import sys
from skills.universal_compressor.compressor import compress, restore, flush_store, stats


TOOLS = {
    "compress": {
        "description": "Conservatively compact content and report measured UTF-8 bytes. Token savings are workload-dependent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to compress"},
                "content_type": {
                    "type": "string",
                    "enum": ["auto", "text", "json", "log", "tool_output", "code"],
                    "description": "Content type hint (auto-detect if 'auto')",
                    "default": "auto",
                },
                "reversible": {
                    "type": "boolean",
                    "description": "Store original for later restoration",
                    "default": False,
                },
            },
            "required": ["content"],
        },
    },
    "restore": {
        "description": "Restore original content from a reversible compression key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Reversible key from compress()"},
            },
            "required": ["key"],
        },
    },
    "compressor_stats": {
        "description": "Get compression store statistics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [
                {"name": name, **schema} for name, schema in TOOLS.items()
            ]},
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "compress":
            result = compress(
                content=arguments.get("content", ""),
                content_type=arguments.get("content_type", "auto"),
                reversible=arguments.get("reversible", False),
                learn=True,
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({
                        "data": result.data,
                        "content_type": result.content_type,
                        "original_size": result.original_size,
                        "compressed_size": result.compressed_size,
                        "ratio": result.ratio,
                        "reversible_key": result.reversible_key,
                        "strategy": result.strategy,
                        "warnings": result.warnings,
                        "grounding_id": result.grounding_id,
                    })}]
                },
            }

        if tool_name == "restore":
            key = arguments.get("key", "")
            original = restore(key)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": original if original is not None else f"No content found for key '{key}'"}]
                },
            }

        if tool_name == "compressor_stats":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(stats())}]
                },
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main():
    """Run MCP server over stdio."""
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
