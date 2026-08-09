"""CLI for read-only portfolio validation and drift reports."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from skills.portfolio_sync.core import (
    PortfolioError,
    compare_github_inventory,
    load_observed_inventory,
    load_registry,
    summarize_registry,
    validate_registry,
)


def _emit_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or compare the read-only Botte portfolio registry."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--registry",
        default="portfolio/projects.json",
        help="Registry JSON path (default: portfolio/projects.json).",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )

    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "validate",
        parents=[common],
        help="Validate schema and safety rules.",
    )
    commands.add_parser(
        "summary",
        parents=[common],
        help="Show deterministic portfolio counts.",
    )

    diff = commands.add_parser(
        "diff",
        parents=[common],
        help="Compare against a pre-fetched GitHub inventory JSON file.",
    )
    diff.add_argument("--observed", required=True, help="Observed repository inventory.")
    diff.add_argument(
        "--owner",
        help="Owner used when observed entries contain only repository names.",
    )
    diff.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with status 1 when a difference is detected.",
    )
    return parser


def _human_validate(report: dict[str, Any]) -> None:
    print(
        "Portfolio registry valid — "
        f"{report['projects']} projects / {report['programs']} programs / "
        f"{report['github_projects']} GitHub sources"
    )


def _human_summary(report: dict[str, Any]) -> None:
    _human_validate(report)
    print("Status:")
    for name, count in report["by_status"].items():
        print(f"  {name:<14} {count}")
    print("Priority:")
    for name, count in report["by_priority"].items():
        print(f"  {name:<14} {count}")


def _human_diff(report: dict[str, Any]) -> None:
    state = "clean" if report["clean"] else f"{report['drift_count']} drift item(s)"
    print(
        f"Portfolio GitHub diff — {state}; "
        f"{report['matched']} matched / {report['observed_github']} observed"
    )
    for field in (
        "missing_in_registry",
        "registered_not_observed",
        "visibility_mismatches",
        "archive_mismatches",
    ):
        values = report[field]
        if not values:
            continue
        print(f"{field}:")
        for value in values:
            print(f"  {value}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        if args.command == "validate":
            result = validate_registry(registry)
        elif args.command == "summary":
            result = summarize_registry(registry)
        else:
            observed = load_observed_inventory(args.observed, owner=args.owner)
            result = compare_github_inventory(registry, observed)
    except PortfolioError as exc:
        if args.json:
            _emit_json({"valid": False, "error": str(exc)})
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _emit_json(result)
    elif args.command == "validate":
        _human_validate(result)
    elif args.command == "summary":
        _human_summary(result)
    else:
        _human_diff(result)

    if args.command == "diff" and args.fail_on_drift and not result["clean"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
