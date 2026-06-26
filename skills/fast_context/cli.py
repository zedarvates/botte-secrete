"""CLI for FastContext — stdlib argparse.

    python -m skills.fast_context.cli explore . "find DB connection patterns"
    python -m skills.fast_context.cli explore /path "understand function: calibrate()"
    python -m skills.fast_context.cli explore . "where are the tests?" --max-results 10
    python -m skills.fast_context.cli explore . "audit security" --verbose
    python -m skills.fast_context.cli explore . "import sqlite3" --format markdown
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.fast_context import explore, cached_explore, discover_query_type


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="fast_context", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("explore", help="Explore a repo with a natural-language query")
    s.add_argument("root", help="Project root path (default: .)", nargs="?", default=".")
    s.add_argument("query", help="What to look for (e.g. 'find DB imports')")
    s.add_argument("--max-results", type=int, default=20,
                   help="Max results to return (default: 20)")
    s.add_argument("--format", choices=["json", "compact", "markdown"],
                   default="compact", help="Output format (default: compact)")
    s.add_argument("--verbose", action="store_true",
                   help="Show query type and stats")
    s.add_argument("--cache", action="store_true",
                   help="Use LRU cache (same query within 30s = cached)")
    s.add_argument("--no-color", action="store_true",
                   help="Disable color output")

    s = sub.add_parser("query-type", help="Detect query type from a query string")
    s.add_argument("query", help="Query string to classify")

    s = sub.add_parser("stats", help="Show cache stats")

    args = p.parse_args(argv)

    if args.cmd == "explore":
        root = Path(args.root).resolve()
        if not root.exists():
            print(f"❌ Root path does not exist: {root}", file=sys.stderr)
            return 1

        qtype = discover_query_type(args.query)

        if args.verbose:
            print(f"🔍 Query: {args.query}")
            print(f"   Type:  {qtype.value}")
            print(f"   Root:  {root}")
            print(f"   Cache: {'enabled' if args.cache else 'disabled'}")
            print()

        if args.cache:
            results = cached_explore(str(root), args.query, args.max_results)
        else:
            results = explore(str(root), args.query, args.max_results)

        if args.format == "json":
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif args.format == "markdown":
            from skills.fast_context.compiler import format_markdown
            print(format_markdown(results, args.query))
        else:
            from skills.fast_context.compiler import format_compact
            output = format_compact(results, args.query)
            if args.no_color:
                # Strip ANSI (none generated, but future-proof)
                pass
            print(output)

        if args.verbose:
            print(f"\n📊 {len(results)} results returned")

        return 0

    elif args.cmd == "query-type":
        qtype = discover_query_type(args.query)
        print(json.dumps({"query": args.query, "type": qtype.value}, ensure_ascii=False))
        return 0

    elif args.cmd == "stats":
        from skills.fast_context.store import default_cache
        cache = default_cache()
        print(json.dumps({
            "size": cache.size,
            "keys": cache.keys,
        }, ensure_ascii=False, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
