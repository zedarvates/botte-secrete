"""Preview or run an isolated comparison of identical focused contract tests.

Run from the repository root with ``python -m scripts.plan_validation_pilot
--run --output <new-report.json>``. The output path is mandatory; existing files
are never replaced. This is a test pilot, not an executor or production ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import statistics
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "parcimonia.plan-validation-pilot/v1"
OBJECTIVE = "All 12 named focused contract tests run once and pass, with no skips."
GROUPS = (
    ("preferences", "PlanPreferencesTests", (
        "test_user_priority_changes_winner_and_preserves_tradeoff",
        "test_hard_budget_cannot_be_outweighed_by_speed",
        "test_unknown_priority_cost_is_undetermined_not_zero")),
    ("selection", "PlanSelectionTests", (
        "test_second_option_is_explicit_choice_and_retains_recommendation",
        "test_changed_cost_priority_goal_and_step_order_reject_stale_digest",
        "test_receipt_tampering_cost_id_steps_digest_and_authority_is_rejected")),
    ("handoff", "PlanHandoffTests", (
        "test_preserves_intact_plan_and_existing_validator_accepts_it",
        "test_rejects_missing_additional_and_duplicate_steps",
        "test_rejects_stale_request_and_now_unavailable_choice")),
    ("verified", "VerifiedRunTests", (
        "test_real_subprocess_artifact_and_compact_evidence",
        "test_precondition_and_source_changes_prevent_execution",
        "test_zero_exit_without_required_artifact_blocks_only_descendants")),
)
TEST_GROUPS = tuple(tuple(f"skills.conductor.test_{module}.{case}.{method}"
                          for method in methods)
                    for module, case, methods in GROUPS)
TEST_IDS = tuple(test for group in TEST_GROUPS for test in group)
SOURCE_FILES = (
    "skills/__init__.py", "skills/atomic_json.py",
    "skills/capabilities/__init__.py", "skills/capabilities/registry.py",
    "skills/conductor/__init__.py", "skills/conductor/conductor.py",
    "skills/conductor/executor.py", "skills/conductor/verified.py",
    "skills/conductor/preferences.py", "skills/conductor/selection.py",
    "skills/conductor/handoff.py", "skills/conductor/test_preferences.py",
    "skills/conductor/test_selection.py", "skills/conductor/test_handoff.py",
    "skills/conductor/test_verified.py", "scripts/plan_validation_pilot.py",
)
LIMITATIONS = [
    "Focused existing fixture tests; no general task-quality or production qualification.",
    "Identical named tests establish only this accepted objective, not full coverage equivalence.",
    "Some existing tests use internal mocks; actual pilot commands and the artifact test use real subprocesses.",
    "Wall times include child startup, test fixtures, Conductor checks and temporary checkpoints.",
    "Setup/report time is reported separately; host reasoning and assessment time are not measured.",
    "No model calls inside the pilot subprocesses does not imply zero host tokens or free compute.",
    "No energy, token, monetary, RAM or human-time measurement; corresponding costs remain unknown.",
    "No traffic or hardware instrumentation; this fixed test selection invokes no services or discovery.",
    "At most three paired runs are a small local calibration, not a global gain or forecast-accuracy study.",
    "Temporary snapshots and checkpoints are deleted; retained reports cannot resume those runs.",
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources_match(root, source_hashes):
    try:
        return all(file_hash(root / name) == sha for name, sha in source_hashes.items())
    except OSError:
        return False


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def strategies():
    return {"batched": (TEST_IDS,), "split": TEST_GROUPS}


def snapshot_sources(source_root, destination):
    """Copy only the audited dependency closure; never write into the source tree."""
    hashes = {}
    for name in SOURCE_FILES:
        payload = (source_root / name).read_bytes()
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    return hashes


def accepted_result(result, expected):
    """Independently reject missing, duplicate, skipped or failed test evidence."""
    return (type(result) is dict and result.get("schema") == "parcimonia.pilot-tests/v1"
            and result.get("requested_test_ids") == list(expected)
            and result.get("executed_test_ids") == list(expected)
            and type(result.get("tests_run")) is int
            and result["tests_run"] == len(expected)
            and result.get("failures") == [] and result.get("errors") == []
            and result.get("skipped") == [] and result.get("expected_failures") == []
            and result.get("unexpected_successes") == []
            and result.get("all_passed") is True)


def run_test_ids(test_ids):
    """Run real unittest methods; retain loader errors and full failure details."""
    class RecordingResult(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.executed = []

        def startTest(self, test):
            self.executed.append(test.id())
            super().startTest(test)

    log = io.StringIO()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name)
                               for name in test_ids)
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=log, resultclass=RecordingResult,
                                     verbosity=2).run(suite)
    payload = {
        "schema": "parcimonia.pilot-tests/v1", "requested_test_ids": list(test_ids),
        "executed_test_ids": result.executed, "tests_run": result.testsRun,
        "failures": [{"test_id": test.id(), "detail": detail} for test, detail in result.failures],
        "errors": [{"test_id": test.id(), "detail": detail} for test, detail in result.errors],
        "skipped": [{"test_id": test.id(), "reason": reason} for test, reason in result.skipped],
        "expected_failures": [{"test_id": test.id(), "detail": detail}
                              for test, detail in result.expectedFailures],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
        "unittest_wall_s": time.perf_counter() - started, "unittest_output": log.getvalue(),
        "all_passed": (result.wasSuccessful() and result.testsRun == len(test_ids)
                       and result.executed == list(test_ids) and not result.skipped
                       and not result.expectedFailures and not result.unexpectedSuccesses),
    }
    return payload


def worker(input_path, output_path):
    request = json.loads(input_path.read_text(encoding="utf-8"))
    ids = request["test_ids"]
    if (type(ids) is not list or not ids or len(ids) != len(set(ids))
            or any(name not in TEST_IDS for name in ids)):
        raise ValueError("worker requires distinct names from the fixed pilot test set")
    result = run_test_ids(ids)
    save_new(output_path, result)
    return 0 if accepted_result(result, ids) else 1


def build_plan(root, strategy, repetition, source_hashes):
    steps = []
    groups = strategies()[strategy]
    for index, ids in enumerate(groups):
        stem = f"work/{strategy}-{repetition}-{index}"
        request_path, result_path = stem + "-input.json", stem + "-result.json"
        save_new(root / request_path, {"test_ids": list(ids)})
        steps.append({
            "id": f"tests-{index}", "capability": "plan-validation-pilot",
            "command": f"python -B scripts/plan_validation_pilot.py --worker {request_path} {result_path}",
            "local": True, "needs": [],
            "requires": [{"kind": "file_sha256", "path": request_path,
                          "value": file_hash(root / request_path)},
                         {"kind": "file_absent", "path": result_path}],
            "ensures": [{"kind": "json_equals", "path": result_path,
                         "pointer": "/" + key, "value": value}
                        for key, value in (("requested_test_ids", list(ids)),
                                           ("executed_test_ids", list(ids)),
                                           ("tests_run", len(ids)), ("failures", []),
                                           ("errors", []), ("skipped", []),
                                           ("expected_failures", []),
                                           ("unexpected_successes", []),
                                           ("all_passed", True))],
            "observes": [result_path], "source_hashes": dict(source_hashes),
        })
    return {"schema": "botte.skill-plan/v1", "goal": OBJECTIVE,
            "context": f"isolated-contract-pilot-{strategy}-{repetition}", "steps": steps}


def run_strategy(root, source_root, strategy, repetition, source_hashes, timeout):
    # Import the existing executor; no alternate command runner is supplied.
    from skills.conductor.verified import execute_verified

    started = time.perf_counter()
    supervisor_before = (sources_match(source_root, source_hashes)
                         and Path(execute_verified.__code__.co_filename).resolve()
                         == source_root / "skills/conductor/verified.py")
    plan = build_plan(root, strategy, repetition, source_hashes)
    preparation = time.perf_counter() - started
    execution = (execute_verified(plan, cwd=str(root), confirm=True, timeout=timeout,
                                  checkpoint=f"work/{strategy}-{repetition}-checkpoint.json")
                 if supervisor_before else
                 {"complete": False, "error": "supervising source binding not satisfied", "results": []})
    supervisor_after = sources_match(source_root, source_hashes)
    elapsed = time.perf_counter() - started
    outputs, errors, executed = [], [], []
    for step, expected in zip(plan["steps"], strategies()[strategy]):
        output = root / step["observes"][0]
        try:
            result = json.loads(output.read_text(encoding="utf-8"))
            outputs.append(result)
            executed.extend(result.get("executed_test_ids", []))
            if not accepted_result(result, expected):
                errors.append({"step_id": step["id"], "reason": "test_evidence_rejected"})
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"step_id": step["id"], "reason": type(exc).__name__, "detail": str(exc)})
    complete = (execution.get("complete") is True and supervisor_before and supervisor_after and not errors
                and executed == list(TEST_IDS))
    dispatch = sum(row["duration_s"] for row in execution.get("results", []))
    return {
        "strategy": strategy, "repetition": repetition, "plan": plan,
        "execution": execution, "test_outputs": outputs, "verification_errors": errors,
        "supervisor_sources_before_match": supervisor_before,
        "supervisor_sources_after_match": supervisor_after,
        "method_preparation_wall_s": preparation,
        "accepted": complete, "wall_s": elapsed, "conductor_step_duration_sum_s": dispatch,
        "conductor_outside_steps_s": max(0.0, elapsed - dispatch),
        "unittest_wall_s": sum(item["unittest_wall_s"] for item in outputs),
        "non_unittest_wall_s": max(0.0, elapsed - sum(item["unittest_wall_s"] for item in outputs)),
        "processes_started": sum(row["started"] for row in execution.get("results", [])),
        "retries": 0, "reused_steps": sum(row["reused"] for row in execution.get("results", [])),
    }


def retrospective_comparison(runs, sources_valid=True, repetitions=None):
    """Use the actual comparator on observations; failed methods stay unknown."""
    from skills.conductor.preferences import METRICS, REQUEST_SCHEMA, propose_plans

    request = {"schema": REQUEST_SCHEMA, "currency": "EUR",
               "projects": [{"id": "contract-validation", "goals": ["verified-12-contract-cases"]}],
               "actions": [], "candidates": [],
               "preferences": {"priorities": [{"metric": "elapsed_minutes"}]}}
    repetitions = repetitions or max((row["repetition"] for row in runs), default=0)
    method_acceptance = {}
    for strategy in strategies():
        observations = [row for row in runs if row["strategy"] == strategy]
        valid = bool(sources_valid and repetitions and len(observations) == repetitions
                     and sorted(row["repetition"] for row in observations) == list(range(1, repetitions + 1))
                     and all(row["accepted"] for row in observations))
        method_acceptance[strategy] = valid
        metrics = {key: None for key in METRICS}
        if valid:
            metrics["elapsed_minutes"] = statistics.median(row["wall_s"] for row in observations) / 60
        run_ids = [row["execution"].get("run_id", "not-dispatched") for row in observations]
        action_id = "validate-" + strategy
        request["actions"].append({"id": action_id, "needs": [], "projects": ["contract-validation"],
                                   "metrics": metrics,
                                   "provenance": {"kind": "measurement", "ref": "paired-runs:" + ",".join(run_ids)}})
        request["candidates"].append({"id": strategy, "steps": [action_id],
                                     "goals": {"contract-validation": ["verified-12-contract-cases"]}})
    started = time.perf_counter()
    proposals = propose_plans(request)
    return {"kind": "retrospective_observed_calibration_not_forecast",
            "request": request, "proposals": proposals,
            "comparison_wall_s": time.perf_counter() - started,
            "all_method_replicates_accepted": method_acceptance,
            "scope": "same 12 fixture cases and same local observations used for calibration; no generalized gain or independent prediction test",
            "failed_method_policy": "elapsed remains null and cannot be recommended when any replicate fails"}


def run_pilot(source_root, *, repetitions=3, timeout=60, run=False):
    if type(repetitions) is not int or not 1 <= repetitions <= 3:
        raise ValueError("repetitions must be an integer from 1 to 3")
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ValueError("timeout must be an integer from 1 to 60 seconds per process")
    started = time.perf_counter()
    source_root = Path(source_root).resolve(strict=True)
    report = {"schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": "run" if run else "preview", "accepted_objective": OBJECTIVE,
              "test_ids": list(TEST_IDS), "repetitions_per_strategy": repetitions,
              "timeout_s_per_process": timeout, "strategy_groups": strategies(),
              "acceptance_policy": "all identical named tests pass in every paired run; zero skips and missing tests",
              "comparison_policy": "reference retained unless all runs accepted and candidate median wall time improves by at least 10%",
              "reference_strategy": "batched", "candidate_strategy": "split",
              "limitations": LIMITATIONS,
              "usage": {"pilot_subprocess_model_calls": 0, "host_tokens": None,
                        "tokens": None, "money": None, "energy_wh": None,
                        "peak_ram_gib": None, "human_minutes": None},
              "environment": {"python": sys.version, "platform": sys.platform},
              "boundaries": {"network_requested": False, "services_started": False,
                             "hardware_discovery": False, "deployment": False,
                             "production_ledger_written": False},
              "runs": [], "failures": [], "active_operations": [], "retries": 0}
    with tempfile.TemporaryDirectory(prefix="parcimonia-plan-pilot-") as temporary:
        root = Path(temporary)
        hashes = snapshot_sources(source_root, root)
        report["source_hashes"] = hashes
        report["input_id"] = digest({"test_ids": TEST_IDS, "source_hashes": hashes,
                                     "strategies": strategies(), "repetitions": repetitions,
                                     "timeout": timeout})
        report["setup_wall_s"] = time.perf_counter() - started
        if run:
            for repetition in range(1, repetitions + 1):
                order = ("batched", "split") if repetition % 2 else ("split", "batched")
                for strategy in order:
                    row = run_strategy(root, source_root, strategy, repetition, hashes, timeout)
                    report["runs"].append(row)
                    if not row["accepted"]:
                        report["failures"].append({"strategy": strategy, "repetition": repetition,
                                                   "reason": "accepted_objective_not_verified"})
                    report["active_operations"].extend(
                        {"strategy": strategy, "repetition": repetition, "step_id": result["id"],
                         "state": "unknown_requires_reconciliation"}
                        for result in row["execution"].get("results", [])
                        if result["status"] in ("running", "uncertain"))
        report["snapshot_sources_unchanged"] = sources_match(root, hashes)
        report["source_tree_files_unchanged"] = sources_match(source_root, hashes)
    report["complete"] = bool(run and not report["failures"]
                              and len(report["runs"]) == repetitions * 2
                              and report["snapshot_sources_unchanged"]
                              and report["source_tree_files_unchanged"])
    if run:
        medians = {name: statistics.median(row["wall_s"] for row in report["runs"]
                                          if row["strategy"] == name) for name in strategies()}
        report["observed_calibration"] = {"kind": "observed_calibration_not_forecast",
                                           "median_wall_s": medians,
                                           "paired_candidate_minus_reference_s": [
                                               next(r["wall_s"] for r in report["runs"] if r["strategy"] == "split" and r["repetition"] == rep)
                                               - next(r["wall_s"] for r in report["runs"] if r["strategy"] == "batched" and r["repetition"] == rep)
                                               for rep in range(1, repetitions + 1)]}
        promote = report["complete"] and medians["split"] <= medians["batched"] * 0.9
        report["decision"] = "candidate_supported_for_this_scope" if promote else "retain_reference"
        report["retrospective_comparison"] = retrospective_comparison(
            report["runs"], report["snapshot_sources_unchanged"] and report["source_tree_files_unchanged"], repetitions)
    else:
        report["decision"] = "preview_only_no_execution_evidence"
    report["total_pilot_wall_s"] = time.perf_counter() - started
    report["timing_scope"] = "setup plus verification runs plus report construction; excludes final serialization and host assessment"
    report["timing_breakdown"] = "wall_s includes method preparation and supervising source guards; step durations include subprocess execution and postchecks; non_unittest_wall_s includes preparation, startup, serialization and all Conductor overhead, not separately instrumented"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute the fixed local test pilot")
    parser.add_argument("--output", type=Path, help="explicit new JSON report path (required)")
    parser.add_argument("--repetitions", type=int, default=3, choices=range(1, 4))
    parser.add_argument("--timeout", type=int, default=60, choices=range(1, 61))
    parser.add_argument("--worker", nargs=2, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if args.worker:
        return worker(*args.worker)
    if args.output is None:
        parser.error("--output is required")
    if args.output.exists():
        parser.error("--output must name a new file")
    report = run_pilot(root, repetitions=args.repetitions, timeout=args.timeout, run=args.run)
    save_new(args.output, report)
    print(json.dumps({"mode": report["mode"], "complete": report["complete"],
                      "runs": len(report["runs"]), "decision": report["decision"],
                      "output": str(args.output)}, ensure_ascii=False))
    return 0 if not args.run or report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
