"""CLI for persistent context windows."""
from __future__ import annotations

import json

from skills.context_windows.windows import ContextWindow, WindowManager

__all__ = ["ContextWindow", "WindowManager"]


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()
    import argparse
    parser = argparse.ArgumentParser(prog="context_windows", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    manager = WindowManager()
    step = sub.add_parser("step", help="Add an active context window")
    step.add_argument("--active", default="")
    step.add_argument("--deltas", type=int, default=0)
    step.set_defaults(func=lambda args: _step(manager, args))
    merge = sub.add_parser("merge", help="Merge selected windows")
    merge.add_argument("--windows", default="active")
    merge.set_defaults(func=lambda args: print(manager.merge(
        [item.strip() for item in args.windows.split(",") if item.strip()])))
    sub.add_parser("stats", help="Show window statistics").set_defaults(
        func=lambda _args: print(json.dumps({"windows": len(manager.windows),
                                              "history": len(manager.history),
                                              "total_tokens": manager.total_tokens()}, indent=2)))
    args = parser.parse_args(argv)
    return args.func(args) or 0


def _step(manager: WindowManager, args) -> None:
    manager.create_window("current", args.active, "active")
    print(manager.load_for_loop(args.deltas))


if __name__ == "__main__":
    raise SystemExit(main())
