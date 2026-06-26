"""CLI for cwe_kb — local CWE knowledge base (0 cloud tokens).

    python -m skills.cwe_kb.cli lookup CWE-78
    python -m skills.cwe_kb.cli match "user input flows into os.system"
    python -m skills.cwe_kb.cli enrich <project>     # taint scan + CWE context
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.cwe_kb import lookup, match, enrich


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="cwe_kb", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    lo = sub.add_parser("lookup", help="exact CWE entry by id")
    lo.add_argument("cwe_id")

    ma = sub.add_parser("match", help="best CWE entries for free text (local embedding)")
    ma.add_argument("text")
    ma.add_argument("--top", type=int, default=3)

    en = sub.add_parser("enrich", help="run the taint scan and attach CWE context")
    en.add_argument("project", nargs="?", default=".")

    args = p.parse_args(argv)

    if args.cmd == "lookup":
        e = lookup(args.cwe_id)
        if not e:
            print(f"ERROR: {args.cwe_id} not in catalog", file=sys.stderr)
            return 1
        print(json.dumps(e, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "match":
        print(json.dumps(match(args.text, top_k=args.top), ensure_ascii=False, indent=2))
        return 0

    # enrich: taint scan → CWE context
    from skills.fallow_like.config import FallowConfig
    from skills.fallow_like.cli import run_analysis
    cfg = FallowConfig(
        project_root=args.project,
        enable_dead_code=False, enable_duplication=False, enable_complexity=False,
        enable_boundaries=False, enable_feature_flags=False, enable_secrets=False,
        enable_hot_paths=False, enable_blast_radius=False,
    )
    findings = run_analysis(cfg).taint
    print(json.dumps({"count": len(findings), "findings": enrich(findings)},
                     ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
