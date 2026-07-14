"""Install Botte Secrète integrations for coding agents."""

from __future__ import annotations

import argparse
import json

from .installer import SUPPORTED_TOOLS, install_plugins


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="botte-plugins")
    parser.add_argument("project")
    parser.add_argument("--tools", nargs="+", choices=SUPPORTED_TOOLS, default=SUPPORTED_TOOLS)
    args = parser.parse_args(argv)
    print(json.dumps(install_plugins(args.project, tools=tuple(args.tools)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
