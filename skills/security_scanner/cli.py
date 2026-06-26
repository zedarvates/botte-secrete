"""CLI for security_scanner — stdlib argparse.

    python -m skills.security_scanner.cli scan skills/ --fail-on critical
    python -m skills.security_scanner.cli scan src/main.py --verbose
    python -m skills.security_scanner.cli scan . --format json --output report.json
    python -m skills.security_scanner.cli audit . --format compact
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.security_scanner import scan_dir, scan_report


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="security_scanner", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="Scan a file or directory for security issues")
    s.add_argument("target", help="File or directory to scan")
    s.add_argument("--fail-on", choices=["critical", "error", "warning", "info"],
                   default="error", help="Minimum severity to fail on (default: error)")
    s.add_argument("--format", choices=["compact", "json", "markdown"],
                   default="compact", help="Output format (default: compact)")
    s.add_argument("--output", "-o", default=None, help="Write output to file")
    s.add_argument("--verbose", "-v", action="store_true", help="Show progress")
    s.add_argument("--no-ast", action="store_true", help="Skip AST analysis")
    s.add_argument("--workers", type=int, default=8, help="Parallel workers")

    s = sub.add_parser("audit", help="Full audit with markdown report")
    s.add_argument("target", help="File or directory to audit")
    s.add_argument("--output", "-o", default=None)
    s.add_argument("--no-ast", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "scan":
        target = str(Path(args.target).resolve())

        if args.verbose:
            print(f"🔍 Scanning: {target}")
            print(f"   Fail-on: {args.fail_on}")
            print(f"   AST:     {'disabled' if args.no_ast else 'enabled'}")

        findings = scan_dir(target, fail_on=args.fail_on,
                            max_workers=args.workers, do_ast=not args.no_ast)
        report = scan_report(findings)

        if args.format == "json":
            output = report.to_json()
        elif args.format == "markdown":
            output = report.markdown()
        else:
            output = report.compact()

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            if args.verbose:
                print(f"   Output written to {args.output}")
        else:
            print(output)

        # Exit with code: 0 = clean, 1 = critical, 2 = errors, 3 = warnings only
        if report.has_critical:
            return 1
        if report.has_errors:
            return 2
        if report.count > 0:
            return 0  # warnings only — still OK
        return 0

    elif args.cmd == "audit":
        target = str(Path(args.target).resolve())
        findings = scan_dir(target, fail_on="info", do_ast=not args.no_ast)
        report = scan_report(findings)
        output = report.markdown()

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
