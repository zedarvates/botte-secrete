"""CLI for botte learn — analyse les sessions et génère des corrections.

Usage:
    python -m skills.botte_learn.cli scan       # Analyser logs + stats
    python -m skills.botte_learn.cli apply      # Écrire les corrections
    python -m skills.botte_learn.cli status     # Voir l'état
    python -m skills.botte_learn.cli scan --stats proxy_stats.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.botte_learn.learner import SessionAnalyzer


def cmd_scan(args: argparse.Namespace):
    """Scan logs and stats for failure patterns."""
    analyzer = SessionAnalyzer()

    print("  🔍 Scanning for patterns...")

    if args.stats:
        analyzer.scan_proxy_stats(Path(args.stats))
    else:
        analyzer.scan_proxy_stats()

    if args.hermes:
        analyzer.scan_hermes_sessions()

    new_rules = analyzer.generate_rules()
    if new_rules:
        print(f"\n  🆕 {len(new_rules)} new rules generated:")
        for rule in new_rules:
            print(f"     • [{rule.rule_id}] {rule.action[:80]}")
    else:
        print("\n  ✅ No new patterns found")

    return 0


def cmd_apply(args: argparse.Namespace):
    """Apply generated rules to AGENTS.md / CLAUDE.md."""
    analyzer = SessionAnalyzer()
    target = args.target
    applied = analyzer.apply_rules(target=target)

    if applied > 0:
        print(f"  ✅ Applied {applied} rules to {'/'.join(args.target) if args.target else 'default files'}")
    else:
        print("  ℹ️  No new rules to apply")

    return 0


def cmd_status(_args: argparse.Namespace):
    """Show current learn status."""
    analyzer = SessionAnalyzer()
    status = analyzer.status()

    print("🧦 Botte Learn — Status")
    print()
    print(f"  Patterns observed: {status['patterns_observed']}")
    print(f"  Rules generated:   {status['rules_generated']}")
    print(f"  Rules applied:     {status['rules_applied']}")
    print()
    if status['by_type']:
        print("  By type:")
        for ptype, count in sorted(status['by_type'].items()):
            print(f"    • {ptype}: {count}")
    print()
    if status['recent_rules']:
        print("  Recent rules:")
        for r in status['recent_rules']:
            status_icon = "✅" if r['applied'] else "⏳"
            print(f"    {status_icon} {r['id']}: {r['trigger'][:50]}")
            print(f"       → {r['action'][:70]}")

    return 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="botte_learn", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    # scan
    s = sub.add_parser("scan", help="Scan logs for failure patterns")
    s.add_argument("--stats", help="Path to proxy stats JSON file")
    s.add_argument("--hermes", action="store_true", help="Also scan Hermes sessions")
    s.set_defaults(func=cmd_scan)

    # apply
    s2 = sub.add_parser("apply", help="Apply correction rules")
    s2.add_argument("--target", choices=["AGENTS.md", "CLAUDE.md"], default="AGENTS.md",
                    help="Target file for rules")
    s2.set_defaults(func=cmd_apply)

    # status
    sub.add_parser("status", help="Show learn status").set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
