"""CLI for Asset Quality Memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skills.asset_quality.memory import evaluate_asset, quality_status, record_verified
from skills.console_utf8 import force_utf8


def _report(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read asset report: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("asset report must contain one JSON object")
    return data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botte asset-qa", description="Shadow k-NN quality memory for assets")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("project", nargs="?", default=".")
    status.add_argument("--json", action="store_true")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("report")
    evaluate.add_argument("--project", default=".")
    evaluate.add_argument("-k", type=int, default=5)
    evaluate.add_argument("--json", action="store_true")
    record = commands.add_parser("record")
    record.add_argument("report")
    record.add_argument("--project", default=".")
    record.add_argument("--verdict", choices=("fail", "uncertain", "pass", "pass-robust"), required=True)
    record.add_argument("--verified-by", required=True)
    record.add_argument("--evidence", action="append", default=[])
    record.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    args = _parser().parse_args(argv)
    try:
        if args.command == "status":
            data = quality_status(args.project)
        elif args.command == "evaluate":
            data = evaluate_asset(_report(args.report), project_root=args.project, k=args.k).to_dict()
        else:
            data = record_verified(_report(args.report), project_root=args.project,
                                   verdict=args.verdict, verified_by=args.verified_by,
                                   evidence_refs=args.evidence)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Asset QA — {data.get('status', data.get('mode'))} · "
                  f"{data.get('verdict', str(data.get('verified_assets')) + ' verified')}")
            print(f"Next: {data.get('reason', data.get('next_action', 'none'))}")
            print("Safety: shadow only; no asset is activated or published.")
        return 0
    except ValueError as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
