"""CLI for the capability registry / curator.

    python -m skills.capabilities.cli map               # ASCII layered system tree
    python -m skills.capabilities.cli list [--json]     # the registry
    python -m skills.capabilities.cli curate "<goal>"   # capabilities for a goal
    python -m skills.capabilities.cli effects skills/capabilities
    python -m skills.capabilities.cli template skills/my_skill --id owner/repo:skills/my_skill
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.capabilities import load, ascii_map, curate
from skills.capabilities.effects import inspect_effects, contract_template


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="capabilities", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("map", help="ASCII layered system tree")
    s = sub.add_parser("list", help="the capability registry")
    s.add_argument("--json", action="store_true")
    s.add_argument("--effects", action="store_true", help="include optional effects declarations")
    s = sub.add_parser("curate", help="capabilities relevant to a goal")
    s.add_argument("goal")
    s = sub.add_parser("effects", help="inspect one skill's effects declaration (read-only)")
    s.add_argument("skill_dir", type=Path)
    s.add_argument("--id", help="expected qualified identity; required for an external tree")
    s.add_argument("--select", action="append", metavar="/SECTION[/INDEX]",
                   help="return an exact section or list entry; repeat for up to 16 selectors")
    s.add_argument("--expect-sha256", help="require the canonical declaration digest from review_before; requires --select")
    s = sub.add_parser("template", help="print a draft effects declaration; does not write files")
    s.add_argument("skill_dir", type=Path)
    s.add_argument("--id", required=True, help="qualified identity, e.g. owner/repo:skills/name")
    args = p.parse_args(argv)

    if args.cmd == "map":
        print(ascii_map())
    elif args.cmd == "list":
        caps = load(include_effects=args.effects)
        if args.json:
            print(json.dumps([c.to_dict() for c in caps], ensure_ascii=False, indent=2))
        else:
            for c in caps:
                suffix = f" [effects: {c.effects['status']}]" if c.effects else ""
                print(f"  [{c.layer:8}] {c.name:24} {c.description[:64]}{suffix}")
    elif args.cmd == "effects":
        if args.expect_sha256 is not None and args.select is None:
            p.error("--expect-sha256 requires --select")
        if args.select is not None:
            from skills.capabilities.review import read_details
            try:
                report = read_details(args.skill_dir, args.select, expected_id=args.id,
                                      expected_sha256=args.expect_sha256)
            except ValueError as exc:
                p.error(str(exc))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["selection_status"] == "selected" else 1
        report = inspect_effects(args.skill_dir, expected_id=args.id)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "declared" else 1
    elif args.cmd == "template":
        try:
            report = contract_template(args.skill_dir, args.id)
        except (OSError, ValueError) as exc:
            p.error(f"Cannot build effects template: {exc}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for c in curate(args.goal):
            print(f"  {c['score']:.2f} [{c['layer']:8}] {c['name']:20} — {c['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
