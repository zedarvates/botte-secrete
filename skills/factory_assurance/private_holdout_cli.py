"""CLI for running a private external holdout without publishing its cases."""

from __future__ import annotations

import argparse
import json
import sys

from .private_holdout import PrivateHoldoutError, run_private_holdout, write_attestation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_set", help="local/private JSON holdout path")
    parser.add_argument("--candidate-sha", required=True, help="40-character candidate git SHA")
    parser.add_argument("--output", required=True, help="public-safe attestation JSON path")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("evaluator", nargs=argparse.REMAINDER, help="evaluator argv after --")
    args = parser.parse_args(argv)

    evaluator = list(args.evaluator)
    if evaluator and evaluator[0] == "--":
        evaluator = evaluator[1:]
    if not evaluator:
        parser.error("evaluator command is required after --")

    try:
        attestation = run_private_holdout(
            private_set_path=args.private_set,
            candidate_sha=args.candidate_sha,
            evaluator_argv=evaluator,
            timeout_seconds=args.timeout,
        )
        write_attestation(attestation, args.output)
    except PrivateHoldoutError as exc:
        print(f"holdout error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"attestation error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "schema": attestation["schema"],
        "set_id": attestation["set_id"],
        "candidate_sha": attestation["candidate_sha"],
        "case_count": attestation["case_count"],
        "status": attestation["status"],
        "contains_cases": False,
        "output": args.output,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if attestation["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
