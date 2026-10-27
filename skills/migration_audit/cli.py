"""CLI for the deterministic migration-completeness gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from skills.atomic_json import write_json
from skills.console_utf8 import force_utf8
from .audit import audit_migration


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    project_default = Path(os.environ.get("BOTTE_PROJECT_ROOT", "."))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", nargs="?", type=Path,
                        help="JSON spec (default: <project>/.botte/migration-audit.json)")
    parser.add_argument("--project", type=Path, default=project_default)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.spec is None:
        spec_path = args.project / ".botte" / "migration-audit.json"
    else:
        spec_path = args.spec if args.spec.is_absolute() else args.project / args.spec
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        result = audit_migration(spec, args.project)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"migration audit unavailable: {exc}", file=sys.stderr)
        return 2
    if args.output:
        write_json(args.output, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        summary = result["summary"]
        print(f"MIGRATION_AUDIT: {result['status']} · {result['reason_code']}")
        print(f"Checks: {summary['passed']} pass, {summary['failed']} fail, "
              f"{summary['uncertain']} uncertain")
    return {"PASS": 0, "FAIL": 1, "UNCERTAIN": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
