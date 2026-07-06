"""CLI for Agent Cache — skip-agent quand output prédictible.

Usage:
    python -m skills.agent_cache.cli check "query" --agent audit
    python -m skills.agent_cache.cli store "query" "response" --agent fix
    python -m skills.agent_cache.cli stats
"""
from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.agent_cache.cache import AgentCache


def cmd_check(args: argparse.Namespace):
    """Check if a response is cached."""
    cache = AgentCache()
    result = cache.exact_match(args.query, args.agent)
    fuzzy = None
    if not result:
        fuzzy = cache.fuzzy_match(args.query, args.agent)

    if result:
        print(f"✅ Exact match — skipping agent")
        if args.verbose:
            print(result)
        return 0
    elif fuzzy:
        print(f"🟡 Fuzzy match (similar query cached) — can skip agent")
        if args.verbose:
            print(fuzzy)
        return 0
    else:
        print(f"❌ No match — must execute agent")
        return 1


def cmd_store(args: argparse.Namespace):
    """Store a response."""
    cache = AgentCache()
    cache.store(
        query=args.query,
        response=args.response,
        agent_type=args.agent,
        fingerprint=args.fingerprint or "",
    )
    print(f"✅ Cached response for '{args.query[:50]}...'")
    return 0


def cmd_stats(_args: argparse.Namespace):
    """Show cache statistics."""
    cache = AgentCache()
    print(json.dumps(cache.stats(), indent=2))
    return 0


def cmd_skip(_args: argparse.Namespace):
    """Predict if agent can be skipped based on fingerprint."""
    # This would be called by the agent pipeline
    print("Check fingerprint and skip if unchanged")


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="agent_cache", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("check", help="Check cache")
    s.add_argument("query", help="Query to check")
    s.add_argument("--agent", default="audit", help="Agent type")
    s.add_argument("--verbose", "-v", action="store_true")
    s.set_defaults(func=cmd_check)

    s2 = sub.add_parser("store", help="Store in cache")
    s2.add_argument("query", help="Original query")
    s2.add_argument("response", help="Response to cache")
    s2.add_argument("--agent", default="audit", help="Agent type")
    s2.add_argument("--fingerprint", help="Code fingerprint")
    s2.set_defaults(func=cmd_store)

    sub.add_parser("stats", help="Show stats").set_defaults(func=cmd_stats)
    sub.add_parser("skip", help="Check skip-ability").set_defaults(func=cmd_skip)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
