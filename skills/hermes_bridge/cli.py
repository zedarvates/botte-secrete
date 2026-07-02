"""CLI for the Hermes bridge.

    python -m skills.hermes_bridge.cli config [--cwd .] [--python python]
    python -m skills.hermes_bridge.cli schemas
    python -m skills.hermes_bridge.cli call botte_auto_route --prompt "hello"
"""

from __future__ import annotations

import argparse
import json

from skills.console_utf8 import force_utf8
from skills.hermes_bridge.bridge import TOOL_SCHEMAS, dispatch, mcp_config


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="hermes_bridge", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("config", help="print the ready-to-paste MCP config entry")
    s.add_argument("--cwd", default=".")
    s.add_argument("--python", default="python")

    sub.add_parser("schemas", help="print the OpenAI-function-calling tool specs")

    s = sub.add_parser("call", help="dispatch one tool by name (for testing the bridge)")
    s.add_argument("tool")
    s.add_argument("--prompt", default="")
    s.add_argument("--query", default="")
    s.add_argument("--strategy", default="")
    s.add_argument("--execute", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "config":
        print(json.dumps(mcp_config(python_exe=args.python, cwd=args.cwd), indent=2))
        return 0
    if args.cmd == "schemas":
        print(json.dumps(TOOL_SCHEMAS, indent=2, ensure_ascii=False))
        return 0

    call_args = {"prompt": args.prompt, "query": args.query,
                 "strategy": args.strategy, "execute": args.execute}
    print(dispatch(args.tool, call_args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
