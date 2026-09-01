"""CLI for typed Botte mission contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.run_contract import (
    ContractError,
    compile_context_manifest,
    contract_fingerprint,
    load_mission,
)


def _write_or_print(payload: dict, output: str | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def main(argv=None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(prog="botte contract", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a mission contract")
    validate.add_argument("mission")
    validate.add_argument("--json", action="store_true")

    context = sub.add_parser("context", help="Compile a context manifest")
    context.add_argument("mission")
    context.add_argument("--project", default=".")
    context.add_argument("--output")

    fingerprint = sub.add_parser("fingerprint", help="Print canonical mission SHA-256")
    fingerprint.add_argument("mission")

    args = parser.parse_args(argv)
    try:
        mission = load_mission(args.mission)
        if args.command == "validate":
            result = {
                "valid": True,
                "schema": mission["schema"],
                "mission_id": mission["mission_id"],
                "fingerprint": contract_fingerprint(mission),
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(
                    f"VALID {result['schema']} {result['mission_id']} "
                    f"{result['fingerprint']}"
                )
            return 0
        if args.command == "context":
            _write_or_print(
                compile_context_manifest(args.project, mission), args.output
            )
            return 0
        if args.command == "fingerprint":
            print(contract_fingerprint(mission))
            return 0
    except ContractError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
