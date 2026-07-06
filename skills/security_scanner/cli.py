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
from skills.security_scanner import scan_file, scan_directory


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _filter_by_severity(issues: list[dict], min_severity: str) -> list[dict]:
    """Keep only issues at or above min_severity."""
    min_level = SEVERITY_ORDER.get(min_severity, 0)
    return [i for i in issues if SEVERITY_ORDER.get(i.get("severity", "low"), 0) >= min_level]


def _format_compact(issues: list[dict], target: str) -> str:
    if not issues:
        return f"✅ {target}: clean\n"
    lines = [f"🔍 {target}: {len(issues)} issue(s)"]
    for i in issues:
        sev = i.get("severity", "?").upper()
        loc = f"{i.get('line', '?')}:{i.get('column', '?')}"
        snippet = i.get("snippet", "")[:60]
        lines.append(f"  [{sev}] L{loc}  {snippet}")
    return "\n".join(lines) + "\n"


def _format_json(issues: list[dict], target: str) -> str:
    return json.dumps({"target": target, "issues": issues, "total": len(issues)}, indent=2)


def _format_markdown(issues: list[dict], target: str) -> str:
    from datetime import datetime
    lines = [f"# 🔬 Security Scan: {target}", f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]
    if not issues:
        lines.append("✅ **Clean** — no issues found.")
        return "\n".join(lines)
    lines.append(f"**{len(issues)} issue(s) detected**\n")
    lines.append("| Severity | Line | Issue | Snippet |")
    lines.append("|----------|------|-------|---------|")
    for i in issues:
        sev = i.get("severity", "?")
        line = i.get("line", "?")
        issue = i.get("issue", "?")
        snippet = i.get("snippet", "")[:40]
        lines.append(f"| {sev} | {line} | {issue} | `{snippet}` |")
    return "\n".join(lines)


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="security_scanner", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="Scan a file or directory for security issues")
    s.add_argument("target", help="File or directory to scan")
    s.add_argument("--fail-on", choices=["critical", "high", "medium", "low", "info"],
                   default="high", help="Minimum severity to report (default: high)")
    s.add_argument("--format", choices=["compact", "json", "markdown"],
                   default="compact", help="Output format (default: compact)")
    s.add_argument("--output", "-o", default=None, help="Write output to file")
    s.add_argument("--verbose", "-v", action="store_true", help="Show progress")

    s = sub.add_parser("audit", help="Full audit with markdown report")
    s.add_argument("target", help="File or directory to audit")
    s.add_argument("--output", "-o", default=None)

    args = p.parse_args(argv)

    target = str(Path(args.target).resolve())
    p_target = Path(target)

    if args.verbose:
        print(f"🔍 Scanning: {target}")

    if p_target.is_file():
        result = scan_file(target)
        issues = result.get("issues", [])
    elif p_target.is_dir():
        result = scan_directory(target)
        issues = result.get("issues", [])
    else:
        print(f"❌ Target not found: {target}", file=sys.stderr)
        return 1

    # Filter by severity (fail-on means min severity to include)
    if args.cmd == "scan":
        min_sev = args.fail_on
        if min_sev == "info":
            displayed = issues
        else:
            displayed = _filter_by_severity(issues, min_sev)
    else:
        displayed = issues

    # Format output
    fmt = getattr(args, "format", "markdown")
    if fmt == "json":
        output = _format_json(displayed, target)
    elif fmt == "markdown" or args.cmd == "audit":
        output = _format_markdown(displayed, target)
    else:
        output = _format_compact(displayed, target)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        if args.verbose:
            print(f"   Output written to {args.output}")
    else:
        print(output)

    # Exit code: 0 = clean, non-zero if critical/high issues
    criticals = sum(1 for i in displayed if i.get("severity") == "critical")
    highs = sum(1 for i in displayed if i.get("severity") == "high")
    if criticals:
        return 1
    if highs:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
