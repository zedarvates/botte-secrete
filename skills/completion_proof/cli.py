"""CLI for completion_proof — policy A11 detector (done without proof).

    python -m skills.completion_proof.cli [<path>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.completion_proof import audit_path
from skills.console_utf8 import force_utf8


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="completion_proof", description=__doc__)
    p.add_argument("path", nargs="?", default=".",
                   help="report file or directory to audit (default: current dir)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    r = audit_path(args.path)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0

    s = r["summary"]
    print(f"A11 completion-proof audit — {r['target']}")
    print(f"   {r['files_scanned']} files · {s['total']} unproven completions\n")
    for f in r["findings"][:15]:
        print(f"   ⚠ {f['preuve']}")
        print(f"      cout: {f['cout_estime']}")
        print(f"      gain: {f['gain_attendu']}")
        print(f"      risque: {f['risque']}")
        print(f"      refactoring minimal: {f['refactoring_minimal']}\n")
    if s["total"] > 15:
        print(f"   … +{s['total'] - 15} autres (voir --json)")
    return 0  # report-only; never fails the build


if __name__ == "__main__":
    raise SystemExit(main())
