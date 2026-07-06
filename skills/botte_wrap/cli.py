"""CLI for botte wrap — wrap/unwrap agents to route through compression proxy.

Usage:
    python -m skills.botte_wrap.cli wrap claude
    python -m skills.botte_wrap.cli wrap codex
    python -m skills.botte_wrap.cli wrap openai
    python -m skills.botte_wrap.cli wrap aider --port 8787 --target http://localhost:11434/v1
    python -m skills.botte_wrap.cli unwrap claude
    python -m skills.botte_wrap.cli list
    python -m skills.botte_wrap.cli status
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from skills.console_utf8 import force_utf8
from skills.botte_wrap.wrappers import (
    AGENTS,
    WrapperState,
    list_available_agents,
    list_wrapped,
    wrap_agent,
    unwrap_agent,
)


def cmd_wrap(args: argparse.Namespace):
    """Wrap an agent to route through the compression proxy."""
    agent = args.agent

    if agent not in AGENTS:
        print(f"❌ Unknown agent: {agent}")
        print(f"   Available: {', '.join(sorted(AGENTS.keys()))}")
        return 1

    result = wrap_agent(
        agent_name=agent,
        proxy_port=args.port,
        target=args.target or os.environ.get("BOTTE_TARGET_URL"),
        api_key=args.api_key or os.environ.get("BOTTE_API_KEY"),
    )

    if result.success:
        return 0
    else:
        print(f"❌ {result.message}")
        return 1


def cmd_unwrap(args: argparse.Namespace):
    """Unwrap an agent."""
    agent = args.agent
    result = unwrap_agent(agent)
    print(result.message)
    return 0


def cmd_list(_args: argparse.Namespace):
    """List wrapped agents."""
    wrapped = list_wrapped()
    if not wrapped:
        print("No agents currently wrapped.")
        print(f"\nAvailable agents: {', '.join(sorted(AGENTS.keys()))}")
        return 0

    print("🧦 Wrapped agents:")
    print(f"{'Agent':<12} {'Name':<25} {'Since':<25} {'Proxy'}")
    print("-" * 80)
    for w in wrapped:
        print(f"{w['agent']:<12} {w['name']:<25} {w['wrapped_since']:<25} :{w['proxy_port']}")
    return 0


def cmd_status(_args: argparse.Namespace):
    """Show botte wrap status."""
    state = WrapperState.load()
    wrapped = list_wrapped()
    available = list_available_agents()

    print("🧦 Botte Secrète — Wrap Status")
    print()
    print(f"Proxy port: {state.proxy_port}")
    print(f"Proxy PID:  {state.proxy_pid or 'unknown'}")

    if wrapped:
        print(f"\nWrapped agents ({len(wrapped)}):")
        for w in wrapped:
            env_str = " ".join(f"{k}={v}" for k, v in w["env_vars"].items())
            print(f"  • {w['name']} → {env_str}")
    else:
        print("\nNo agents wrapped.")

    if available:
        print(f"\nAvailable to wrap: {', '.join(available)}")
    else:
        print(f"\nNo agents found in PATH. Install one to use `wrap`.")
        print(f"  Available agents: {', '.join(sorted(AGENTS.keys()))}")

    return 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="botte_wrap", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    # wrap
    s = sub.add_parser("wrap", help="Wrap an agent to use the compression proxy")
    s.add_argument("agent", choices=sorted(AGENTS.keys()),
                   help="Agent to wrap")
    s.add_argument("--port", type=int, default=8787,
                   help="Proxy port (default: 8787)")
    s.add_argument("--target", help="Upstream LLM endpoint (default: $BOTTE_TARGET_URL)")
    s.add_argument("--api-key", help="API key for upstream (default: $BOTTE_API_KEY)")
    s.set_defaults(func=cmd_wrap)

    # unwrap
    s2 = sub.add_parser("unwrap", help="Unwrap an agent")
    s2.add_argument("agent", choices=sorted(AGENTS.keys()),
                    help="Agent to unwrap")
    s2.set_defaults(func=cmd_unwrap)

    # list
    sub.add_parser("list", help="List wrapped agents").set_defaults(func=cmd_list)

    # status
    sub.add_parser("status", help="Show wrap status").set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
