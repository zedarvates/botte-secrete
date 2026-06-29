#!/usr/bin/env python3
"""audit_dag CLI — build the canonical DAG and emit both views.

    # from a findings JSON (list of {rule_id, severity, message, file, line, fix_hint})
    python -m skills.audit_dag.cli build findings.json --out audit.html

    # or scan THIS repo with fallow_like and build (dogfood)
    python -m skills.audit_dag.cli scan skills/ --out audit.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from skills.console_utf8 import force_utf8
    force_utf8()
except Exception:  # noqa: BLE001
    pass

from skills.audit_dag import build_dag, to_compact, to_html


def _emit(findings, out, title):
    dag = build_dag(findings)
    print(to_compact(dag))                      # machine view → stdout (for an LLM/pipe)
    if out:
        Path(out).write_text(to_html(dag, title=title), encoding="utf-8")
        print(f"\n[html] {out}  (grade {dag.grade}, {len(dag.nodes)} findings)",
              file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="audit_dag")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build from a findings JSON file")
    b.add_argument("findings")
    b.add_argument("--out", help="write the human HTML here")
    s = sub.add_parser("scan", help="scan a path with fallow_like, then build")
    s.add_argument("path")
    s.add_argument("--out", help="write the human HTML here")
    args = p.parse_args(argv)

    if args.cmd == "build":
        data = json.loads(Path(args.findings).read_text(encoding="utf-8"))
        findings = data.get("findings", data) if isinstance(data, dict) else data
        return _emit(findings, args.out, f"Audit — {args.findings}")

    if args.cmd == "scan":
        try:
            from skills.fallow_like.scanner import scan as fallow_scan  # type: ignore
            findings = fallow_scan(args.path)  # best-effort; shape may vary by version
        except Exception as e:  # noqa: BLE001
            print(f"fallow_like scan unavailable ({e}); pass a findings JSON to `build`.",
                  file=sys.stderr)
            return 1
        return _emit(findings, args.out, f"Audit — {args.path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
