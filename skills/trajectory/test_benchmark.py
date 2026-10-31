#!/usr/bin/env python3
"""Focused tests for the leakage-resistant Quality Compass benchmark."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skills.trajectory import cli
from skills.trajectory.benchmark import (
    BenchmarkConfig,
    MissionValidationError,
    benchmark_report,
    load_missions,
    temporal_split,
)


def _row(index: int, *, dataset_class: str = "fixture") -> dict:
    train = index < 60
    family_index = index // 5 if train else 20 + (index - 60) // 4
    local = index % 2 == 0
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    kind = "routine summary" if local else "system design"
    return {
        "schema": "botte.quality-routing-mission/v1",
        "id": f"qm_{index:012x}",
        "family_id": f"qf_{family_index:012x}",
        "observed_at": observed.isoformat(),
        "task": f"SANITIZED_CANARY_{index:03d} {kind} verified case",
        "task_type": "simple_qa" if local else "system_design",
        "expected_route": "local" if local else "cloud",
        "verdict": "PASS",
        "verified_by": "pytest:routing-fixture",
        "evidence_refs": [f"pytest:routing-{index}"],
        "dataset_class": dataset_class,
        "sanitized": True,
        "contains_private_data": False,
    }


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value)) if value else set()
    return set()


def main() -> int:
    state = [0, 0]

    def ok(message: str, condition: bool) -> None:
        print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
        state[0 if condition else 1] += 1

    print("== quality routing benchmark tests ==")

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        report = benchmark_report(project)
        ok("missing verified missions produces an explicit gap report",
           report["benchmark_status"] == "insufficient_evidence"
           and report["comparative_winner"] is None
           and any(gap["code"] == "no_replayable_missions" for gap in report["gaps"]))
        ok("every mechanism recommends collecting data without a holdout",
           all(item["recommendation"] == "collect_more_data"
               for item in report["routing_quality"].values()))
        ok("routing, model and harness quality stay separate",
           report["model_quality"]["status"] == "not_observed"
           and report["harness_quality"]["status"] == "not_observed"
           and all(item["metric"] for item in report["missing_metrics"]))
        ok("learned authority is blocked even in the report",
           report["authority"] == {
               "shadow_only": True, "acted": False, "trained": False,
               "activation_allowed": False,
           })

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        mission_path = root / "missions.jsonl"
        _write(mission_path, [_row(index) for index in range(80)])
        missions = load_missions(mission_path)
        train, holdout, gaps = temporal_split(missions, BenchmarkConfig())
        ok("temporal split keeps oldest train and newest holdout",
           len(train) == 60 and len(holdout) == 20 and not gaps
           and train[-1].observed_at < holdout[0].observed_at)
        ok("task families are disjoint across the temporal boundary",
           not ({item.family_id for item in train} & {item.family_id for item in holdout}))

        report = benchmark_report(root, mission_path, code_ref="fixture-ref")
        routing = report["routing_quality"]
        ok("all three mechanisms see the exact same holdout",
           report["benchmark_status"] == "measured_fixture"
           and {routing[name]["holdout_missions"] for name in routing} == {20}
           and {routing[name]["quality_scope"] for name in routing} == {"routing_oracle_only"})
        ok("fixture labels can test the harness but cannot manufacture a winner",
           report["dataset"]["eligible_for_conclusions"] is False
           and report["comparative_winner"] is None
           and all(routing[name]["recommendation"] == "collect_more_data" for name in routing))
        ok("cold/warm latency, abstention and disagreement are measured",
           all(routing[name]["latency_ms"]["cold_first"] is not None for name in routing)
           and routing["micro_nn"]["abstention_rate"] is not None
           and report["disagreement"]["status"] == "measured")
        ok("missing resource metrics remain explicit rather than zero-filled",
           all(routing[name]["vram_peak_mb"] is None for name in routing)
           and {"vram_peak", "energy"}.issubset(
               {item["metric"] for item in report["missing_metrics"]}
           ))
        encoded = json.dumps(report)
        ok("report omits task text, fingerprints and local storage paths",
           "SANITIZED_CANARY" not in encoded
           and "task_fingerprint" not in _keys(report)
           and str(root) not in encoded)
        ok("report pins mission, harness, policy and model digests",
           report["reproducibility"]["code_ref"] == "fixture-ref"
           and all(len(report["reproducibility"][key]) == 64 for key in (
               "mission_set_sha256", "benchmark_harness_sha256",
               "quality_module_sha256", "micro_nn_model_sha256",
           )))

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        rows = [_row(index) for index in range(80)]
        rows[-1]["task"] = rows[0]["task"]
        path = root / "duplicate.jsonl"
        _write(path, rows)
        report = benchmark_report(root, path)
        ok("exact task leakage rejects the benchmark",
           report["benchmark_status"] == "rejected_for_leakage"
           and any(gap["code"] == "exact_task_leakage" for gap in report["gaps"]))

        rows = [_row(index) for index in range(80)]
        rows[-1]["family_id"] = rows[0]["family_id"]
        path = root / "family.jsonl"
        _write(path, rows)
        report = benchmark_report(root, path)
        ok("task-family leakage rejects the benchmark",
           report["benchmark_status"] == "rejected_for_leakage"
           and any(gap["code"] == "task_family_leakage" for gap in report["gaps"]))

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        unsafe = _row(0)
        unsafe["task"] = "inspect /workspace/private/project.txt"
        path = root / "unsafe.jsonl"
        _write(path, [unsafe])
        try:
            load_missions(path)
            blocked = False
        except MissionValidationError as error:
            blocked = error.code == "unsanitized_task"
        ok("mission loader rejects local paths and private material", blocked)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        output = root / "gap.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli.main([
                "benchmark", "--project", str(root), "--output", str(output), "--json",
            ])
        payload = json.loads(stdout.getvalue())
        saved = json.loads(output.read_text(encoding="utf-8"))
        ok("CLI emits and saves the same machine-readable gap report",
           rc == 0 and payload["schema"] == saved["schema"]
           and payload["benchmark_status"] == "insufficient_evidence")

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
