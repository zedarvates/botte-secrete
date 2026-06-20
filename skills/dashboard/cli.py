"""CLI: python -m skills.dashboard.cli [<project>] [--json]"""
from __future__ import annotations
import argparse, json, sys
from skills.console_utf8 import force_utf8
from skills.dashboard.dashboard import generate, collect


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="dashboard", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    if args.json:
        print(json.dumps(collect(args.project), ensure_ascii=False, indent=2)); return 0
    paths = generate(args.project, fmt="both")
    print("📊 Dashboard saved:\n   " + "\n   ".join(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
