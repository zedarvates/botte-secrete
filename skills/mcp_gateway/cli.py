"""CLI for mcp_gateway — test et debug du MCP gateway.

    python -m skills.mcp_gateway.cli list
    python -m skills.mcp_gateway.cli call security_scanner '{"root": "."}'
    python -m skills.mcp_gateway.cli call fast_context '{"root": ".", "query": "find imports"}'
    python -m skills.mcp_gateway.cli call botte_nn '{"model": "effort_classifier", "input": [0.1, 0.2, 0.8, 0.0]}'
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.mcp_gateway.server import MCPServer


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="mcp_gateway", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all available MCP tools")

    s = sub.add_parser("call", help="Call a tool with JSON arguments")
    s.add_argument("tool_name", help="Tool name (e.g., security_scanner)")
    s.add_argument("arguments", help="JSON object of arguments")

    sub.add_parser("serve", help="Start MCP server (stdio)")

    args = p.parse_args(argv)

    server = MCPServer()

    if args.cmd == "list":
        print("Available MCP tools:")
        print(f"{'Name':<25} {'Description'}")
        print("-" * 80)
        for t in server.tools:
            print(f"  {t['name']:<23} {t['description'][:60]}...")
        print(f"\nTotal: {len(server.tools)} tools")
        return 0

    elif args.cmd == "call":
        try:
            arguments = json.loads(args.arguments)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}", file=sys.stderr)
            return 1

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": args.tool_name, "arguments": arguments},
        }
        result = server.handle(request)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    elif args.cmd == "serve":
        from skills.mcp_gateway.server import serve_stdio
        serve_stdio()
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
