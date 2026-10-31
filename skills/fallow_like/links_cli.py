"""Check supplied Markdown and a repository path inventory without fetching targets.

    python -m skills.fallow_like.links_cli input.json
    python -m skills.fallow_like.links_cli - < input.json
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.fallow_like.local_links import check_local_links

MAX_INPUT_BYTES = 32 * 1024 * 1024
_FIELDS = {"documents", "available_paths", "inventory_complete", "max_links"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON constants are unsupported")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="JSON input file, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            with open(args.input, "rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("JSON input exceeds 32 MiB")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                             parse_constant=_constant)
        if not isinstance(payload, dict) or set(payload) - _FIELDS:
            raise ValueError("input must contain only local-link API arguments")
        report = check_local_links(**payload)
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    if report["status"] == "partial":
        return 3
    return 1 if report["counts"]["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
