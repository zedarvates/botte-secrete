"""Quality Compass CLI: verified outcomes and shadow k-NN advice."""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.trajectory.quality import advise_route, quality_status, record_verified

_COMMANDS = {"status", "advise", "record"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="botte qa",
        description=(
            "Learn from externally verified outcomes and explain a shadow-only "
            "k-NN route suggestion. No suggestion is executed automatically."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="show readiness and the single next step")
    status.add_argument("project", nargs="?", default=".")
    status.add_argument("--json", action="store_true")

    advise = sub.add_parser("advise", help="compare a task with verified neighbors")
    advise.add_argument("task")
    advise.add_argument("--project", default=".")
    advise.add_argument("--task-type", default="")
    advise.add_argument("--tag", action="append", default=[])
    advise.add_argument("--risk", choices=("low", "standard", "high", "critical"),
                        default="standard")
    advise.add_argument("-k", type=int, default=7)
    advise.add_argument("--json", action="store_true")

    record = sub.add_parser("record", help="record one externally verified outcome")
    record.add_argument("task")
    record.add_argument("--project", default=".")
    record.add_argument("--route", choices=("deterministic", "local", "cloud", "human"),
                        required=True)
    record.add_argument("--verdict", choices=("fail", "uncertain", "pass", "pass-robust"),
                        required=True)
    record.add_argument("--verified-by", required=True,
                        help="tests, schema, deterministic, replay, human, independent, or benchmark")
    record.add_argument("--quality-score", type=float)
    record.add_argument("--risk", choices=("low", "standard", "high", "critical"),
                        default="standard")
    record.add_argument("--task-type", default="")
    record.add_argument("--tag", action="append", default=[])
    record.add_argument("--model", default="")
    record.add_argument("--harness", default="")
    record.add_argument("--duration-ms", type=float)
    record.add_argument("--cost-usd", type=float)
    record.add_argument("--tokens", type=int)
    record.add_argument("--evidence", action="append", default=[], required=True,
                        help="external evidence reference; repeat for multiple references")
    record.add_argument("--json", action="store_true")
    return parser


def _print_status(data: dict) -> None:
    print(f"🧭 QA Compass — {data['mode'].upper()} · {data['readiness']}")
    duplicate_note = ""
    if data["recorded_outcomes"] != data["verified_samples"]:
        duplicate_note = f" ({data['recorded_outcomes']} recorded; duplicates collapsed)"
    print(
        f"   Verified support: {data['verified_samples']}/{data['g2_min_verified']}"
        f"{duplicate_note}"
    )
    routes = data["by_route"]
    print(
        "   Routes: "
        + " · ".join(f"{name} {routes[name]}" for name in ("deterministic", "local", "cloud", "human"))
    )
    print(f"   Next: {data['next_action']}")
    print("   Safety: shadow only; raw task text is not stored.")


def _print_advice(data: dict) -> None:
    if data["status"] == "suggest":
        print(f"🧭 Shadow suggestion: {data['recommendation']}")
        print(
            f"   Evidence strength: {data['evidence_strength']:.0%} · "
            f"{data['neighbor_count']} similar verified outcome(s)"
        )
    elif data["status"] == "gated":
        print("🛑 Human approval gate")
    else:
        print(f"🧭 No suggestion — {data['status']}")
    print(f"   Why: {data['reason']}")
    print("   Action: none; the current deterministic router remains in control.")


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["status"]
    elif argv[0] == "--json":
        argv = ["status", *argv]
    elif argv[0] not in _COMMANDS and argv[0] not in ("-h", "--help"):
        # One obvious path: `botte qa "task"` means `advise`.
        argv = ["advise", *argv]
    args = _parser().parse_args(argv)

    try:
        if args.command == "status":
            data = quality_status(args.project)
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_status(data)
            return 0

        if args.command == "advise":
            data = advise_route(
                args.task,
                project_root=args.project,
                task_type=args.task_type,
                tags=args.tag,
                risk=args.risk,
                k=args.k,
            ).to_dict()
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_advice(data)
            return 0

        record = record_verified(
            args.task,
            project_root=args.project,
            route=args.route,
            verdict=args.verdict,
            verified_by=args.verified_by,
            quality_score=args.quality_score,
            risk=args.risk,
            task_type=args.task_type,
            tags=args.tag,
            model=args.model,
            harness=args.harness,
            duration_ms=args.duration_ms,
            cost_usd=args.cost_usd,
            tokens=args.tokens,
            evidence_refs=args.evidence,
        )
        if args.json:
            print(json.dumps(record, ensure_ascii=False, indent=2))
        else:
            print(f"✅ Verified outcome recorded: {record['id']} · {record['route']} · {record['verdict']}")
            print("   Raw task text was transformed locally and was not stored.")
        return 0
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
