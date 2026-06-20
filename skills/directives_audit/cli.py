"""CLI for directives_audit — stdlib argparse.

    python -m skills.directives_audit.cli <project_dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.directives_audit.directives import audit


def _force_utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


_ICON = {"crit": "🔴", "err": "🟠", "warn": "🟡", "info": "🔵"}


def main(argv=None) -> int:
    _force_utf8()
    p = argparse.ArgumentParser(prog="directives_audit", description=__doc__)
    p.add_argument("project", nargs="?", default=".", help="project directory")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped report under <project>/.botte/reports/")
    args = p.parse_args(argv)

    report = audit(Path(args.project))
    if args.save:
        from skills.report import save
        save("directives", report, fmt=args.save,
             out_dir=Path(report["project"]) / ".botte" / "reports",
             title=f"Directives audit — {report['project']}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["has_instructions"] else 1

    print(f"📋 Directives audit — {report['project']}")
    print(f"   Score: {report['score']}/100   Files: {report['files_found']}   "
          f"by kind: {report['by_kind']}")
    if report["files"]:
        print("\n   Found:")
        for f in report["files"]:
            print(f"     • {f['path']:42s} [{f['tool']} · {f['fmt']} · ~{f['tokens_est']} tok]")
    if report["findings"]:
        print("\n   Findings:")
        for fnd in report["findings"]:
            print(f"     {_ICON.get(fnd['severity'], '•')} {fnd['path']}: {fnd['message']}")
            if fnd["fix_hint"]:
                print(f"        ↳ {fnd['fix_hint']}")
    else:
        print("\n   ✅ No issues.")
    return 0 if report["has_instructions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
