"""CLI for Botte Proxy — transparent LLM compression proxy.

Usage:
    python -m skills.botte_proxy.cli proxy --port 8787
    python -m skills.botte_proxy.cli proxy --target http://localhost:11434/v1 --port 8787
    python -m skills.botte_proxy.cli proxy --target https://api.openai.com/v1 --api-key $OPENAI_API_KEY
    python -m skills.botte_proxy.cli proxy --target https://api.anthropic.com/v1 --api-key $ANTHROPIC_API_KEY
    python -m skills.botte_proxy.cli stats
"""
from __future__ import annotations

import argparse
import json
import sys
import os

from skills.console_utf8 import force_utf8
from skills.botte_proxy.proxy_server import run_proxy, get_stats


def cmd_proxy(args: argparse.Namespace):
    """Start the botte proxy server."""
    run_proxy(
        host=args.host,
        port=args.port,
        target_url=args.target,
        api_key=args.api_key or os.environ.get("BOTTE_API_KEY"),
    )


def cmd_stats(_args: argparse.Namespace):
    """Show proxy statistics as JSON."""
    stats = get_stats()
    print(json.dumps(stats.to_dict(), indent=2))


def cmd_dashboard(args: argparse.Namespace):
    """Start proxy with dashboard mode (auto-opens browser)."""
    import webbrowser
    run_proxy(
        host=args.host,
        port=args.port,
        target_url=args.target,
        api_key=args.api_key or os.environ.get("BOTTE_API_KEY"),
    )


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="botte_proxy", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    # proxy subcommand
    s = sub.add_parser("proxy", help="Start the compression proxy server")
    s.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    s.add_argument("--port", type=int, default=8787, help="Listen port (default: 8787)")
    s.add_argument("--target", default="http://localhost:11434/v1",
                    help="Upstream LLM API endpoint (default: http://localhost:11434/v1)")
    s.add_argument("--api-key", help="API key for upstream (default: $BOTTE_API_KEY)")
    s.set_defaults(func=cmd_proxy)

    # stats subcommand
    s2 = sub.add_parser("stats", help="Show proxy statistics")
    s2.set_defaults(func=cmd_stats)

    # dashboard subcommand
    s3 = sub.add_parser("dashboard", help="Start proxy with dashboard at /dashboard")
    s3.add_argument("--host", default="0.0.0.0", help="Bind address")
    s3.add_argument("--port", type=int, default=8787, help="Listen port")
    s3.add_argument("--target", default="http://localhost:11434/v1",
                    help="Upstream LLM API endpoint")
    s3.add_argument("--api-key", help="API key for upstream")
    s3.set_defaults(func=cmd_proxy)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
