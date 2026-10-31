#!/usr/bin/env python3
"""Focused offline tests for CI outcome envelopes and public summaries."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.trajectory.ci import emit_ci_outcome
from skills.trajectory.outcome import load_outcomes
from skills.trajectory.quality import load_verified

ROOT = Path(__file__).resolve().parents[2]


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _emit(project: str, tests: str, docs: str, **kwargs) -> dict:
    return emit_ci_outcome(
        tests_outcome=tests,
        docs_outcome=docs,
        run_id=kwargs.get("run_id", "PRIVATE_RUN_761"),
        run_attempt="1",
        job="test-python",
        python_version="3.12",
        project_root=project,
        public_output=Path(project) / "public-ci.json",
    )


def main() -> int:
    state = [0, 0]
    print("== CI outcome envelope tests ==")

    with tempfile.TemporaryDirectory() as project:
        first = _emit(project, "success", "success")
        replay = _emit(project, "success", "success")
        rows = load_outcomes(project)
        _ok("successful tests and docs emit verified PASS_ROBUST",
            len(rows) == 1 and rows[0]["status"] == "PASS_ROBUST"
            and rows[0]["verified"] is True
            and first["trajectory"] is not None, state)
        _ok("replayed CI job cannot inflate verified grounding",
            replay["deduplicated"] is True and len(load_verified(project)) == 1,
            state)
        _ok("CI envelope remains shadow-only despite verified evidence",
            rows[0]["shadow_only"] is True
            and rows[0]["activation_allowed"] is False, state)

        public_path = Path(project) / "public-ci.json"
        public_raw = public_path.read_text(encoding="utf-8")
        public = json.loads(public_raw)
        _ok("public summary exposes only state, reason, and next safe action",
            public["state"] == "grounded" and public["verified"] is True
            and public["privacy"] == {
                "raw_task": False, "execution_fingerprint": False,
                "local_path": False, "evidence_detail": False,
            }, state)
        _ok("public summary omits run ids, fingerprints, paths, and evidence detail",
            "PRIVATE_RUN_761" not in public_raw
            and "task_fingerprint" not in public_raw
            and "github-actions:" not in public_raw
            and str(Path(project)) not in public_raw, state)

    with tempfile.TemporaryDirectory() as project:
        failed = _emit(project, "failure", "skipped")
        _ok("failed test step emits independently verified FAIL",
            failed["envelope"]["status"] == "FAIL"
            and failed["envelope"]["verified"] is True
            and failed["public"]["state"] == "failing", state)

    with tempfile.TemporaryDirectory() as project:
        cancelled = _emit(project, "cancelled", "skipped")
        _ok("cancelled CI emits verified uncertainty, never PASS",
            cancelled["envelope"]["status"] == "UNCERTAIN"
            and cancelled["envelope"]["verified"] is True
            and cancelled["public"]["state"] == "uncertain", state)

    with tempfile.TemporaryDirectory() as project:
        partial = _emit(project, "success", "skipped")
        _ok("skipped required check emits unverified PARTIAL",
            partial["envelope"]["status"] == "PARTIAL"
            and partial["envelope"]["verified"] is False
            and partial["trajectory"] is None
            and partial["public"]["state"] == "collecting", state)

    invalid = False
    with tempfile.TemporaryDirectory() as project:
        try:
            _emit(project, "unknown", "success")
        except ValueError:
            invalid = True
    _ok("unobserved CI vocabulary is rejected", invalid, state)

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    _ok("primary CI emits after observed test failure without masking it",
        "id: tests" in workflow and "id: docs" in workflow
        and "if: always() && steps.tests.outcome != ''" in workflow
        and "python -m skills.trajectory.ci" in workflow, state)
    _ok("CI uploads only the sanitized outcome artifact",
        "path: .botte-cache/ci-outcome-public.json" in workflow
        and ".botte/quality-outcomes.jsonl" not in workflow, state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
