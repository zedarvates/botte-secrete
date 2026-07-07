"""CLI for Token Shaper — shaping dynamique per-turn.

Usage:
    python -m skills.token_shaper.cli shape "query" --agent audit
    python -m skills.token_shaper.cli shape "query" --json
    python -m skills.token_shaper.cli stats
"""
from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.token_shaper.shaper import TokenShaper


def cmd_shape(args: argparse.Namespace):
    """Shape a query."""
    shaper = TokenShaper()
    config = shaper.shape(args.query, args.agent)

    if args.json:
        print(json.dumps({
            "level": config.level.value,
            "compress_ratio": config.compress_ratio,
            "output_tokens_target": config.output_tokens_target,
            "verbosity_steer": config.verbosity_steer,
        }, indent=2))
    else:
        print(f"Level: {config.level.value}")
        print(f"Compression: {config.compress_ratio:.0%}")
        print(f"Output target: {config.output_tokens_target} tokens")
        if config.verbosity_steer:
            print(f"Steer: {config.verbosity_steer}")


def cmd_stats(_args: argparse.Namespace):
    """Show shaping statistics."""
    shaper = TokenShaper()
    print(json.dumps(shaper.stats(), indent=2))


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="token_shaper", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("shape", help="Shape a query")
    s.add_argument("query", help="Query to shape")
    s.add_argument("--agent", default="", help="Agent type")
    s.add_argument("--json", action="store_true", help="JSON output")
    s.set_defaults(func=cmd_shape)

    sub.add_parser("stats", help="Show stats").set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
