"""CLI for Prefix Pruner — élague les sections inutilisées du contexte.

Usage:
    python -m skills.prefix_pruner.cli prune < fichier.txt
    python -m skills.prefix_pruner.cli prune --input context.txt --strategy aggressive
    python -m skills.prefix_pruner.cli tree
    python -m skills.prefix_pruner.cli stats
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.prefix_pruner.pruner import PrefixTree, prune_content


def cmd_prune(args: argparse.Namespace):
    """Prune context content."""
    content = Path(args.input).read_text() if args.input else sys.stdin.read()

    tree = PrefixTree()
    result = prune_content(content, tree, strategy=args.strategy)

    if args.output:
        Path(args.output).write_text(result)
        print(f"  ✍️ Written to {args.output}")
    else:
        print(result)


def cmd_tree(_args: argparse.Namespace):
    """Show prefix tree."""
    tree = PrefixTree()
    data = {sid: {"type": s.section_type, "use": s.use_count,
                   "skip": s.skip_count, "usefulness": round(s.usefulness, 2)}
            for sid, s in tree.sections.items()}
    print(json.dumps(data, indent=2))


def cmd_stats(_args: argparse.Namespace):
    """Show pruning stats."""
    tree = PrefixTree()
    print(json.dumps(tree.stats(), indent=2))


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="prefix_pruner", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("prune", help="Prune content")
    s.add_argument("--input", help="Input file (default: stdin)")
    s.add_argument("--output", help="Output file (default: stdout)")
    s.add_argument("--strategy", choices=["auto", "aggressive", "conservative"],
                   default="auto", help="Pruning strategy")
    s.set_defaults(func=cmd_prune)

    sub.add_parser("tree", help="Show prefix tree").set_defaults(func=cmd_tree)
    sub.add_parser("stats", help="Show stats").set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
