"""CLI for the deterministic Factory Assurance Layer."""

from __future__ import annotations

import argparse
import json

from .assurance import evaluate_assurance, load_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Factory Assurance run record")
    parser.add_argument("run", help="Path to a JSON assurance run record")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    result = evaluate_assurance(load_run(args.run))
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["status"] == "review_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
