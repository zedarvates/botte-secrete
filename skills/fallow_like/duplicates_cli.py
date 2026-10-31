"""Bounded read-only exact-file duplicate report, without optional analyzers.

    python -m skills.fallow_like.duplicates_cli /explicit/project
"""

from __future__ import annotations

import argparse
import json

from skills.console_utf8 import force_utf8
from skills.fallow_like.file_duplicates import find_file_duplicates


def main(argv=None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Explicit directory to inspect; required")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--max-file-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-entries", type=int, default=20000)
    parser.add_argument("--max-depth", type=int, default=20)
    parser.add_argument("--exclude-dir", action="append", dest="exclude_dirs",
                        help="Directory basename to exclude; repeated values replace defaults")
    args = parser.parse_args(argv)
    try:
        result = find_file_duplicates(**vars(args))
    except (ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 3 if result["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
