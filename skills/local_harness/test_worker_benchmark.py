"""Hermetic tests for the local-worker benchmark."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .worker_benchmark import (
    BenchmarkInputError, HostTelemetry, Observation, load_plan, run_benchmark,
)


def _ok(message, condition, state):
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


class _Telemetry(HostTelemetry):
    def start(self):
        self.peak_ram_bytes = 1024
        self.peak_vram_mib = {"0": 5120}

    def stop(self):
        pass


def main() -> int:
    state = [0, 0]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan = root / "plan.json"
        missions = root / "missions.jsonl"
        report_path = root / "report.json"
        plan.write_text(json.dumps({
            "schema": "botte.local-worker-benchmark-plan/v1", "authority": "SIMULATE",
            "endpoint": "http://127.0.0.1:11434", "models": [
                {"id": "granite", "model": "granite42-q4km", "family": "granite-4.2-8b",
                 "quantization": "Q4_K_M", "source_uri": "https://example.invalid/granite"},
                {"id": "baseline", "model": "qwen-local", "family": "qwen",
                 "quantization": "Q4", "source_uri": "local:verified"},
            ], "repetitions": 1, "warmup": 0,
        }), encoding="utf-8")
        rows = [
            {"schema": "botte.local-worker-benchmark-mission/v1", "mission_id": "extract-1",
             "family": "extract", "role": "SCOUT", "prompt": "PRIVATE_CANARY",
             "verified_by": "human-review", "evidence_ref": "fixture-extract",
             "expected": {"json_subset": {"answer": 3}}},
            {"schema": "botte.local-worker-benchmark-mission/v1", "mission_id": "requirements-1",
             "family": "requirements", "role": "REQUIREMENTS", "prompt": "REQUIREMENTS_CANARY",
             "verified_by": "human-review", "evidence_ref": "fixture-requirements",
             "expected": {"escalate": False}},
            {"schema": "botte.local-worker-benchmark-mission/v1", "mission_id": "tool-1",
             "family": "tool-use", "role": "SCOUT", "prompt": "TOOL_CANARY",
             "verified_by": "human-review", "evidence_ref": "fixture-tool",
             "tools": [{"type": "function", "function": {"name": "inspect_repo", "parameters": {"type": "object"}}}],
             "expected": {"tool_name": "inspect_repo"}},
            {"schema": "botte.local-worker-benchmark-mission/v1", "mission_id": "validate-1",
             "family": "validation", "role": "VALIDATOR", "prompt": "SECOND_CANARY",
             "verified_by": "human-review", "evidence_ref": "fixture-validator",
             "expected": {"validator_verdict": "PASS"}},
        ]
        missions.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

        def caller(_plan, model, mission):
            bodies = {
                "extract-1": {"answer": 3}, "requirements-1": {"escalate": False},
                "tool-1": {}, "validate-1": {"verdict": "PASS"},
            }
            return Observation(content=json.dumps(bodies[mission.id]),
                               tool_names=["inspect_repo"] if mission.id == "tool-1" else [], completion_tokens=10,
                               prompt_tokens=10, ttft_ms=20, duration_ms=120)

        report = run_benchmark(plan, missions, caller=caller, telemetry_factory=_Telemetry)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        public = report_path.read_text(encoding="utf-8")
        _ok("two workers use the exact same sanitized missions", len(report["models"]) == 2, state)
        _ok("all required worker roles remain bounded", report["dataset"]["roles"] == ["REQUIREMENTS", "SCOUT", "VALIDATOR"], state)
        _ok("TTFT and throughput are measured", all(
            value["metrics"]["ttft_ms"]["median"] == 20
            and value["metrics"]["throughput_tokens_s"]["median"] == 100
            for value in report["models"].values()), state)
        _ok("RAM and per-GPU VRAM are observed without pooling", all(
            value["metrics"]["host_ram_used_peak_bytes"] == 1024
            and value["metrics"]["gpu_vram_used_peak_mib"] == {"0": 5120}
            for value in report["models"].values()), state)
        _ok("quality metrics are independently scored", all(
            value["metrics"]["mission_success"] == 1.0
            and value["metrics"]["validator_disagreement"] == 0.0
            for value in report["models"].values()), state)
        _ok("complete comparative telemetry yields a measured report",
            report["benchmark_status"] == "measured_comparable", state)
        _ok("raw prompts and responses never enter the report",
            "PRIVATE_CANARY" not in public and "SECOND_CANARY" not in public
            and "REQUIREMENTS_CANARY" not in public and "TOOL_CANARY" not in public
            and "127.0.0.1" not in public
            and report["dataset"]["raw_prompts_in_report"] is False, state)
        _ok("benchmark cannot promote or act", report["authority"] == {
            "mode": "SIMULATE", "acted": False, "trained": False,
            "activation_allowed": False, "builder_promotion_allowed": False,
        }, state)

        missing = run_benchmark(
            plan, missions,
            caller=lambda *_: Observation(error_code="ENDPOINT_UNAVAILABLE"),
            telemetry_factory=lambda _: HostTelemetry(10),
        )
        _ok("unavailable workers fail closed", missing["benchmark_status"] == "insufficient_evidence"
            and missing["authority"]["activation_allowed"] is False, state)

        unsafe = json.loads(plan.read_text(encoding="utf-8"))
        unsafe["endpoint"] = "https://public.example.com"
        plan.write_text(json.dumps(unsafe), encoding="utf-8")
        rejected = False
        try:
            load_plan(plan)
        except BenchmarkInputError:
            rejected = True
        _ok("public endpoints are rejected for local-worker evidence", rejected, state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
