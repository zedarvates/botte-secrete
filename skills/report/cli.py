"""CLI to browse saved audit reports.

    python -m skills.report.cli list [--dir .botte/reports] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.report import list_reports


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="report", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list", help="list saved reports (most recent first)")
    s.add_argument("--dir", default=".botte/reports")
    s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    rows = list_reports(Path(args.dir))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return 0
    if not rows:
        print(f"No reports in {args.dir} (run an audit with --save)."); return 0
    print(f"📑 {len(rows)} report(s) in {args.dir}:")
    for r in rows:
        print(f"   {r['when']}  {r['name']:20} .{r['fmt']:4}  {r['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
