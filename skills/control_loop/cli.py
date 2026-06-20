"""CLI for the control loop.

    python -m skills.control_loop.cli analyze [--json]
    python -m skills.control_loop.cli adapt [--apply]
    python -m skills.control_loop.cli reset
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.control_loop.control_loop import analyze, adapt, apply, reset_thresholds, load
from skills.auto_router.effort import load_thresholds


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="control_loop", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("analyze", help="aggregate the routing ledger")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("adapt", help="compute (and optionally apply) new thresholds")
    s.add_argument("--apply", action="store_true")
    sub.add_parser("reset", help="restore default thresholds")
    args = p.parse_args(argv)

    if args.cmd == "analyze":
        st = analyze()
        print(json.dumps(st, ensure_ascii=False, indent=2) if args.json else
              f"samples={st.get('samples',0)} local={st.get('local_pct','?')}% "
              f"escalation={st.get('escalation_rate','?')} success={st.get('success_rate','?')} "
              f"saved={st.get('tokens_saved_total',0)} tok")
        return 0
    if args.cmd == "adapt":
        a = adapt()
        print(f"current : {load_thresholds()}")
        print(f"proposed: {a['thresholds']}  (changed={a['changed']})")
        print(f"why     : {a['why']}")
        if args.apply and a["changed"]:
            print(f"applied → {apply(a['thresholds'])}")
        return 0
    reset_thresholds()
    print(f"thresholds reset to default → {load_thresholds()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
