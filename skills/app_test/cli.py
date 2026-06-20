"""CLI for app_test — generate/run local image-matching GUI tests (SikuliX).

    python -m skills.app_test.cli gen  <spec.json>            # print the SikuliX script
    python -m skills.app_test.cli run  <spec.json> [--out DIR] # generate + run if SikuliX present
"""

from __future__ import annotations

import argparse
import json
import sys
from skills.console_utf8 import force_utf8

from skills.app_test.generator import load_spec, to_sikulix_script, run



def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="app_test", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("gen", help="print the generated SikuliX script")
    s.add_argument("spec")

    s = sub.add_parser("run", help="generate + run (if SikuliX installed)")
    s.add_argument("spec"); s.add_argument("--out", default=".")

    args = p.parse_args(argv)

    if args.cmd == "gen":
        print(to_sikulix_script(load_spec(args.spec)))
        return 0

    r = run(args.spec, out_dir=args.out)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ran") and r.get("passed", True) else (0 if not r.get("ran") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
