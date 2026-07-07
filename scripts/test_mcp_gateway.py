#!/usr/bin/env python3
"""Test the MCP Gateway protocol end-to-end.

Sends JSON-RPC messages to the MCP server via subprocess with stdin pipe.
Tests: initialize, tools/list, tools/call (botte_nn), notifications, ping.

Usage:
    python3 scripts/test_mcp_gateway.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skills.console_utf8 import force_utf8  # noqa: E402 — avant tout print d'émoji

force_utf8()

REPO = Path(__file__).resolve().parent.parent


def mcp_request(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Send a single JSON-RPC request to the MCP server via stdin pipe."""
    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        request["params"] = params

    payload = json.dumps(request) + "\n"

    # sys.executable, pas "python3" (stub Windows Store) ; env hérité + PYTHONPATH
    # ajouté — {"PYTHONPATH": ...} seul écrasait PATH/SYSTEMROOT et pouvait
    # empêcher l'interpréteur de démarrer sur Windows.
    result = subprocess.run(
        [sys.executable, "-m", "skills.mcp_gateway.server"],
        cwd=str(REPO),
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )

    if result.stdout:
        return json.loads(result.stdout.strip())
    if result.stderr:
        return {"error": result.stderr.strip()}
    return {"error": "no output"}


def main():
    print("🔌 MCP Gateway Protocol Test")
    print("=" * 50)

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name} — {detail}")

    # 1. Initialize
    resp = mcp_request("initialize", {}, req_id=1)
    check("initialize returns protocolVersion",
          resp.get("result", {}).get("protocolVersion") == "2024-11-05",
          str(resp.get("error", "")))
    check("initialize server name",
          resp.get("result", {}).get("serverInfo", {}).get("name") == "botte-gateway",
          str(resp.get("result", {}).get("serverInfo", {})))
    check("initialize has tools capability",
          resp.get("result", {}).get("capabilities", {}).get("tools") is not None)

    # 2. tools/list
    resp = mcp_request("tools/list", req_id=2)
    tools = resp.get("result", {}).get("tools", [])
    check("tools/list returns list", isinstance(tools, list), str(type(tools)))
    check("tools/list has >= 10 tools", len(tools) >= 10, f"got {len(tools)}")
    check("tools have name/description/inputSchema",
          all("name" in t and "description" in t and "inputSchema" in t for t in tools[:3]))

    # Check for specific tools
    tool_names = [t["name"] for t in tools]
    for required in ["security_scanner", "fast_context", "meta_harness", "botte_nn",
                     "solvers", "infra_advisor", "nlp_deterministic", "metrics"]:
        check(f"tool '{required}' is available", required in tool_names)

    # 3. tools/call — botte_nn (fast inference)
    resp = mcp_request("tools/call", {
        "name": "botte_nn",
        "arguments": {"model": "effort_classifier", "input": [0.1, 0.2, 0.8, 0.0]},
    }, req_id=3)
    check("botte_nn call returns result", "result" in resp, str(resp.get("error", "")))
    if "result" in resp:
        content = resp["result"].get("content", [{}])
        text = content[0].get("text", "") if content else ""
        check("botte_nn returns prediction or label", 
              text.startswith("[") or "Prediction:" in text or "Input:" in text,
              f"got: {text[:50]}")
        check("botte_nn produces meaningful output",
              len(text) > 10,
              text[:80])

    # 4. Ping
    resp = mcp_request("ping", req_id=4)
    check("ping returns result", "result" in resp, str(resp.get("error", "")))

    # 5. Unknown method
    resp = mcp_request("unknown_method", req_id=5)
    check("unknown method returns error", "error" in resp)

    # 6. Unknown tool
    resp = mcp_request("tools/call", {
        "name": "nonexistent_tool",
        "arguments": {},
    }, req_id=6)
    check("nonexistent tool returns error", "error" in resp)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
