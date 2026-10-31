"""Deterministic ApproxSpatial fixture runner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .oracle import SpatialEvidence, evaluate_less_than

SCHEMA = "botte.approx-spatial-benchmark/v1"
FIXTURES = Path(__file__).with_name("fixtures.json")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run(fixtures_path: Path = FIXTURES) -> dict:
    raw = fixtures_path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    results = []
    for case in payload["cases"]:
        query = case["query"]
        if query.get("op") != "lt":
            raise ValueError(f"unsupported query op: {query.get('op')!r}")
        evidence = SpatialEvidence.from_mapping(case)
        actual = evaluate_less_than(evidence, query["threshold_m"]).value
        results.append({
            "id": case["id"],
            "expected": case["expected"],
            "actual": actual,
            "pass": actual == case["expected"],
            "evidence": evidence.to_dict(),
            "query": query,
        })
    digest = hashlib.sha256(_canonical(results).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "fixture_schema": payload.get("schema"),
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "results_sha256": digest,
        "summary": {
            "total": len(results),
            "passed": sum(bool(row["pass"]) for row in results),
            "failed": sum(not bool(row["pass"]) for row in results),
        },
        "results": results,
    }


def render_human(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "ApproxSpatial-0A1 deterministic oracle",
        f"fixtures: {summary['total']}  passed: {summary['passed']}  failed: {summary['failed']}",
        f"fixture_sha256: {report['fixture_sha256']}",
        f"results_sha256: {report['results_sha256']}",
    ]
    for row in report["results"]:
        mark = "PASS" if row["pass"] else "FAIL"
        lines.append(f"[{mark}] {row['id']}: expected={row['expected']} actual={row['actual']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit canonical machine-readable JSON")
    args = parser.parse_args(argv)
    report = run()
    print(_canonical(report) if args.json else render_human(report))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
