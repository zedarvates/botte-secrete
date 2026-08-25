"""botte — the packaged console entry point.

One command instead of ~90 `python -m skills.<module>.cli` invocations:

    botte doctor [path]        full project health checkup
    botte route "<prompt>"     0-token routing decision (local vs cloud)
    botte dashboard [path]     cost/savings dashboard (HTML, --tui, --fleet)
    botte bootstrap <path>     deploy botte into a project
    botte checkup [path]       drift checkup (doctor without machine scan)
    botte mcp                  run the MCP server (stdio JSON-RPC)
    botte belt                 verify the 11 micro-NN models
    botte qa [task]            quality compass (verified k-NN shadow)
    botte gain [path]          show measured project cost/savings metrics
    botte discover [path]      find optimization opportunities
    botte version              print the installed version

Every subcommand delegates argv unchanged to the module's own CLI, so their
`--help` and flags keep working: `botte doctor --help`.
"""

from __future__ import annotations

import sys

from skills import __version__
from skills.console_utf8 import force_utf8

_COMMANDS = {
    "doctor": ("skills.checkup.cli", "checkup + machine scan + ranked actions"),
    "checkup": ("skills.checkup.cli", "drift checkup"),
    "route": ("skills.auto_router.cli", "0-token routing decision"),
    "dashboard": ("skills.dashboard.cli", "cost/savings dashboard"),
    "bootstrap": ("skills.bootstrap.cli", "deploy botte into a project"),
    "mcp": ("skills.llm_mcp.server", "MCP server (stdio)"),
    "belt": ("skills.auto_router.checkup_belt2", "verify the 11 micro-NN"),
    "qa": ("skills.trajectory.cli", "verified quality compass (shadow only)"),
    "gain": ("skills.metrics.cli", "show measured cost/savings metrics"),
    "discover": ("skills.infra_advisor.cli", "find optimization opportunities"),
}


def _usage() -> str:
    lines = [f"botte {__version__} — token optimization toolkit", "",
             "Usage: botte <command> [args...]", ""]
    for name, (_, desc) in _COMMANDS.items():
        lines.append(f"  {name:<10} {desc}")
    lines.append(f"  {'version':<10} print the installed version")
    lines.append("")
    lines.append("Any other skill stays reachable as `python -m skills.<module>.cli`.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        return 0
    cmd = argv[0]
    if cmd in ("version", "--version", "-V"):
        print(__version__)
        return 0
    entry = _COMMANDS.get(cmd)
    if entry is None:
        print(f"Unknown command: {cmd}\n\n{_usage()}", file=sys.stderr)
        return 2

    module_name = entry[0]
    import importlib
    import runpy

    rest = argv[1:]
    # auto_router.cli expects its own `route` subcommand: `botte route "x"`
    # must become `auto_router route "x"`, not swallow the verb.
    if cmd == "route" and (not rest or rest[0] not in ("route", "run", "providers", "fusion")):
        rest = ["route", *rest]
    if cmd == "discover" and (not rest or rest[0] not in ("auto", "tips")):
        rest = ["auto", *rest]

    module = importlib.import_module(module_name)
    fn = getattr(module, "main", None)
    if callable(fn):
        try:
            rc = fn(rest)
        except TypeError:
            # some mains read sys.argv themselves (no argv parameter)
            sys.argv = [f"botte {cmd}", *rest]
            rc = fn()
        return int(rc or 0)
    # module runs at import/__main__ time only (e.g. checkup_belt2)
    sys.argv = [f"botte {cmd}", *rest]
    runpy.run_module(module_name, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
