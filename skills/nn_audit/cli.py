"""CLI for nn_audit — are the micro-NNs grounded or synthetic copies of rules?

    python -m skills.nn_audit.cli [<botte_nn dir>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.nn_audit import audit_models


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="nn_audit", description=__doc__)
    p.add_argument("path", nargs="?", default="skills/botte_nn",
                   help="path to the botte_nn dir (default: skills/botte_nn)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    r = audit_models(args.path)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    s = r["summary"]
    print(f"🧠 NN audit — {r['botte_nn']}")
    print(f"   {s['grounded']}/{s['total']} grounded ({s['grounded_pct']}%) · "
          f"{s['synthetic']} synthetic · {s.get('orphan', 0)} orphan · "
          f"{s['at_risk']} at-risk (synthetic+wired)\n")
    for m in r["models"]:
        icon = "✅" if m["data_source"] == "real" else ("⚠️" if m["risk"] else "💤")
        wired = "wired" if m["wired"] else "orphan"
        flags = []
        if not m["has_provenance"]:
            flags.append("no-provenance")
        if not m["has_test_guard"]:
            flags.append("no-test-guard")
        tail = f"  [{', '.join(flags)}]" if flags else ""
        print(f"   {icon} {m['model']:20} {wired:6} — {m['verdict']}{tail}")
        if m["usage"]:
            print(f"        used by: {', '.join(m['usage'][:4])}")
    print("\n   at-risk = synthetic net that drives behaviour → ground it on real data; "
          "orphan synthetic → delete or wire.")
    return 0  # report-only; never fails the build


if __name__ == "__main__":
    raise SystemExit(main())
