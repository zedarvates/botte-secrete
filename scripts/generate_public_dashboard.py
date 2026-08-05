#!/usr/bin/env python3
"""Build a sanitized static dashboard artifact for GitHub Pages."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skills.atomic_json import write_json
from skills.dashboard.api import load_test_summary


DEFAULT_OUTPUT = REPO / ".botte-cache" / "public-dashboard"


def public_metrics(test_summary_path: str | Path | None = None) -> dict:
    """Return repository-only metrics safe for a public static artifact."""
    tests = load_test_summary(test_summary_path)
    return {
        "schema_version": 1,
        "snapshot_scope": "public_repository",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tests_passed": tests["passed"],
        "tests_failed": tests["failed"],
        "tests_status": tests["status"],
        "tests_partial": tests["partial"],
        "tests_stale": tests["stale"],
        "tests_updated_at": tests["generated_at"],
        "tests_git_sha": tests["git_sha"],
        "test_suites": tests["suite_count"],
        # Local operational metrics are intentionally excluded from Pages.
        "lines_saved": 0,
        "avoidable_pct": 0,
        "total_tasks": 0,
        "by_rung": {},
        "memory_entries": 0,
        "memory_projects": 0,
        "memory_by_status": {},
        "memory_by_asset": {},
        "legacy_memory_entries": 0,
        "local_metrics_included": False,
    }


def build(output: str | Path = DEFAULT_OUTPUT,
          test_summary_path: str | Path | None = None) -> list[Path]:
    """Write the static UI and its sanitized JSON payload."""
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)

    source_html = REPO / "skills" / "dashboard" / "index.html"
    index_path = target / "index.html"
    index_path.write_text(source_html.read_text(encoding="utf-8"), encoding="utf-8")

    data_path = target / "dashboard-data.json"
    write_json(data_path, public_metrics(test_summary_path))
    return [index_path, data_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the sanitized Botte Secrète public dashboard",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--test-summary", type=Path)
    args = parser.parse_args(argv)
    paths = build(args.output, args.test_summary)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
