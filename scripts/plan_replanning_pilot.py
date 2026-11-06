"""Preview or run a small, isolated real checkpoint/replanning demonstration.

``python -m scripts.plan_replanning_pilot --run --output <new-report.json>``
explicitly permits only this fixed temporary-file pilot. The default previews
without subprocesses. This is neither an executor nor a production ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "parcimonia.plan-replanning-pilot/v1"
SOURCE_FILES = (
    "skills/__init__.py", "skills/atomic_json.py",
    "skills/capabilities/__init__.py", "skills/capabilities/registry.py",
    "skills/conductor/__init__.py", "skills/conductor/conductor.py",
    "skills/conductor/executor.py", "skills/conductor/verified.py",
    "skills/conductor/preferences.py", "skills/conductor/selection.py",
    "skills/conductor/handoff.py", "skills/conductor/replanning.py",
    "scripts/plan_replanning_pilot.py",
)
CHECKPOINT = "work/checkpoint.json"
ARTIFACTS = {"stage-a": "A verified\n", "stage-b": "B verified\n"}
WORKER = '''"""Fixed trusted worker; writes only this temporary project's files."""
import json
import sys
from pathlib import Path

stage = sys.argv[1]
if stage not in ("stage-a", "stage-b"):
    raise SystemExit("unknown stage")
if stage == "stage-b":
    if not Path("ready.flag").is_file():
        raise SystemExit("ready.flag is missing")
    if Path("stage-a.txt").read_text(encoding="utf-8") != "A verified\\n":
        raise SystemExit("stage A evidence changed")
counter = Path(stage + "-counter.json")
count = json.loads(counter.read_text(encoding="utf-8"))["count"] if counter.exists() else 0
counter.write_text(json.dumps({"count": count + 1}) + "\\n", encoding="utf-8")
Path(stage + ".txt").write_text("A verified\\n" if stage == "stage-a" else "B verified\\n", encoding="utf-8")
'''
LIMITATIONS = [
    "One fixed local two-step demonstration, not general task-quality or production qualification.",
    "The first stop is an unstarted precondition block, not a real process interruption.",
    "The reviewer recommends only; explicit pilot authority and existing Conductor confirmation permit writes.",
    "Only the original immutable execution plan resumes; the reviewer grants no execution authority.",
    "Current local checks cover listed files only; hashes establish consistency, not authentication.",
    "Declared planning estimates are synthetic; observed wall time is not a speed or resource saving.",
    "No energy, tokens, money, peak RAM or human-time measurement; these costs remain unknown.",
    "No services, network, models, robots or production resources are invoked by this fixed worker.",
    "Temporary projects and checkpoints are deleted; this report cannot resume those runs.",
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sources_match(root, hashes):
    try:
        return all(file_hash(root / name) == sha for name, sha in hashes.items())
    except OSError:
        return False


def snapshot_sources(source_root, destination):
    hashes = {}
    for name in SOURCE_FILES:
        payload = (source_root / name).read_bytes()
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    return hashes


def project_files(root):
    return {path.relative_to(root).as_posix(): file_hash(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def build_project(root, hashes):
    """Supply a fixed trusted worker and original plan, never generated commands."""
    (root / "worker.py").write_text(WORKER, encoding="utf-8")
    bindings = {**hashes, "worker.py": file_hash(root / "worker.py")}
    steps = []
    for identifier, content in ARTIFACTS.items():
        steps.append({
            "id": identifier, "capability": "plan-replanning-pilot",
            "command": f"python -B worker.py {identifier}", "local": True,
            "needs": ["stage-a"] if identifier == "stage-b" else [],
            "requires": [{"kind": "file_exists", "path": "ready.flag"}]
                        if identifier == "stage-b" else [],
            "ensures": [
                {"kind": "file_sha256", "path": identifier + ".txt",
                 "value": hashlib.sha256(content.encode("utf-8")).hexdigest()},
                {"kind": "json_equals", "path": identifier + "-counter.json",
                 "pointer": "/count", "value": 1},
            ],
            "observes": [identifier + ".txt", identifier + "-counter.json"],
            "source_hashes": dict(bindings),
        })
    return {"schema": "botte.skill-plan/v1", "goal": "Verify two fixed local artifacts once",
            "context": "isolated-replanning-resume-v1", "steps": steps}


def build_envelope(plan):
    from skills.conductor.handoff import prepare_plan_handoff
    from skills.conductor.preferences import METRICS, REQUEST_SCHEMA, propose_plans
    from skills.conductor.selection import select_plan

    request = {
        "schema": REQUEST_SCHEMA, "currency": "EUR",
        "projects": [{"id": "local-pilot", "goals": ["both-artifacts"]}],
        "actions": [{
            "id": step["id"], "needs": list(step["needs"]), "projects": ["local-pilot"],
            "metrics": {metric: 1 if metric == "elapsed_minutes" else
                        0 if metric == "money" else None for metric in METRICS},
            "provenance": {"kind": "estimate", "ref": "synthetic-pilot-estimate-not-measurement"},
        } for step in plan["steps"]],
        "candidates": [{"id": "two-stages", "steps": [step["id"] for step in plan["steps"]],
                        "goals": {"local-pilot": ["both-artifacts"]}}],
        "preferences": {"priorities": [{"metric": "elapsed_minutes"}]},
    }
    receipt = select_plan(request, "two-stages", propose_plans(request)["input_digest"])
    handoff = prepare_plan_handoff(request, receipt, plan)
    current = deepcopy(request)
    current["preferences"]["priorities"] = [{"metric": "money"}, {"metric": "elapsed_minutes"}]
    return {"schema": "parcimonia.plan-replanning/v1", "previous_request": request,
            "previous_handoff": handoff, "current_request": current,
            "budget_scope": "remaining_work"}


def review_readonly(envelope, root):
    from skills.conductor.replanning import review_plan_replanning

    before = project_files(root)
    envelope_before = digest(envelope)
    started = time.perf_counter()
    review = review_plan_replanning(envelope, CHECKPOINT, cwd=str(root))
    elapsed = time.perf_counter() - started
    after = project_files(root)
    return {"review": review, "wall_s": elapsed,
            "checkpoint_bytes_sha256_before": before[CHECKPOINT],
            "checkpoint_bytes_sha256_after": after.get(CHECKPOINT),
            "checkpoint_bytes_unchanged": before[CHECKPOINT] == after.get(CHECKPOINT),
            "all_project_files_unchanged": before == after,
            "envelope_unchanged": envelope_before == digest(envelope)}


def compact_execution(report):
    """Keep hashes of full evidence and material outcomes without repeated source lists."""
    keys = ("schema", "run_id", "plan_sha256", "context_sha256", "mode", "complete",
            "summary", "coverage", "child_cost", "error")
    result = {key: report[key] for key in keys if key in report}
    result["full_report_sha256"] = digest(report)
    result["results"] = []
    for row in report.get("results", []):
        kept = {key: row[key] for key in ("id", "status", "started", "reused", "exit_code",
                                         "duration_s", "note", "changed_paths", "dependencies")
                if key in row}
        for group in ("source_checks", "source_checks_after", "precondition_checks",
                      "postcondition_checks", "resume_checks", "resume_sources",
                      "resume_precondition_checks"):
            if group in row:
                kept[group] = {"count": len(row[group]),
                               "all_passed": all(check["passed"] for check in row[group]),
                               "failed": [check for check in row[group] if not check["passed"]]}
        result["results"].append(kept)
    return result


def counters(root):
    return {identifier: json.loads((root / (identifier + "-counter.json")).read_text(
            encoding="utf-8"))["count"] if (root / (identifier + "-counter.json")).exists() else 0
            for identifier in ARTIFACTS}


def _expect(report, label, condition):
    report["checks"][label] = bool(condition)
    if not condition:
        report["failures"].append({"check": label, "reason": "expected_local_evidence_not_verified"})


def run_pilot(source_root, *, run=False, timeout=10):
    if type(run) is not bool or type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError("run must be a boolean and timeout an integer from 1 to 30")
    started = time.perf_counter()
    source_root = Path(source_root).resolve()
    report = {
        "schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execution" if run else "preview", "complete": False,
        "authorization_scope": "Explicit --run authorizes this fixed temporary-file pilot only; confirm=true remains required by Conductor.",
        "scenario": ["execute A; B is blocked unstarted by absent ready.flag",
                     "create ready.flag within pilot authority; review without writes",
                     "resume identical plan/checkpoint; A reused, B executes once",
                     "corrupt A; review and existing resume detect stale evidence without replay"],
        "source_hashes": {}, "worker_sha256": hashlib.sha256(WORKER.encode("utf-8")).hexdigest(),
        "checks": {}, "failures": [], "phases": [], "active_operations": [],
        "usage": {"elapsed_wall_s": None, "tokens": None, "money": None,
                  "energy_wh": None, "peak_ram_gib": None, "human_minutes": None},
        "gain_claim": None, "limitations": list(LIMITATIONS),
    }
    if not run:
        report["decision"] = "preview_only_no_execution_evidence"
        report["total_pilot_wall_s"] = time.perf_counter() - started
        return report

    with tempfile.TemporaryDirectory(prefix="botte-replanning-pilot-") as temporary:
        root = Path(temporary)
        hashes = {}
        try:
            hashes = snapshot_sources(source_root, root)
            report["source_hashes"] = hashes
            from skills.conductor.replanning import review_plan_replanning
            from skills.conductor.verified import execute_verified

            supervisor_bound = all(Path(function.__code__.co_filename).resolve() == source_root / name
                                   for function, name in ((execute_verified, "skills/conductor/verified.py"),
                                                          (review_plan_replanning, "skills/conductor/replanning.py")))
            _expect(report, "supervising_sources_before_match",
                    supervisor_bound and sources_match(source_root, hashes))
            if not report["checks"]["supervising_sources_before_match"]:
                raise ValueError("supervising source binding not satisfied")
            plan = build_project(root, hashes)
            original_plan = deepcopy(plan)
            envelope = build_envelope(plan)
            report["original_plan"] = original_plan
            report["planning_inputs"] = {"previous_request": envelope["previous_request"],
                                         "current_request": envelope["current_request"],
                                         "previous_handoff_id": envelope["previous_handoff"]["handoff_id"],
                                         "budget_scope": envelope["budget_scope"]}
            phase_start = time.perf_counter()
            first = execute_verified(plan, cwd=str(root), confirm=True, timeout=timeout,
                                     checkpoint=CHECKPOINT)
            report["phases"].append({"name": "initial_real_execution", "wall_s": time.perf_counter() - phase_start,
                                      "execution": compact_execution(first), "counters": counters(root)})
            rows = {row["id"]: row for row in first.get("results", [])}
            _expect(report, "initial_A_verified_B_blocked_unstarted",
                    rows.get("stage-a", {}).get("status") == "verified"
                    and rows.get("stage-b", {}).get("status") == "blocked"
                    and rows["stage-b"]["started"] is False
                    and counters(root) == {"stage-a": 1, "stage-b": 0})

            (root / "ready.flag").write_text("explicit fixed-pilot authority\n", encoding="utf-8")
            reviewed = review_readonly(envelope, root)
            report["phases"].append({"name": "readonly_replanning_after_flag", **reviewed})
            candidate = next((item for item in reviewed["review"].get("candidates", [])
                              if item["id"] == "two-stages"), {})
            _expect(report, "review_preserves_checkpoint_and_project",
                    reviewed["checkpoint_bytes_unchanged"] and reviewed["all_project_files_unchanged"]
                    and reviewed["envelope_unchanged"])
            _expect(report, "review_recommends_without_selection_or_authority",
                    reviewed["review"].get("recommended_candidate_id") == "two-stages"
                    and reviewed["review"].get("selected_candidate_id") is None
                    and reviewed["review"].get("execution_authorized") is False)
            _expect(report, "review_identifies_A_reusable_B_remaining",
                    candidate.get("reused_action_ids") == ["stage-a"]
                    and candidate.get("remaining_action_ids") == ["stage-b"]
                    and candidate.get("resume_compatible") is True)
            incremental = candidate.get("incremental_totals", {})
            _expect(report, "remaining_work_estimates_exclude_A_and_preserve_unknowns",
                    incremental.get("elapsed_minutes") == 1 and incremental.get("money") == 0
                    and all(incremental.get(metric) is None
                            for metric in ("tokens", "energy_wh", "peak_ram_gib", "human_minutes")))

            phase_start = time.perf_counter()
            resumed = execute_verified(plan, cwd=str(root), confirm=True, timeout=timeout,
                                       checkpoint=CHECKPOINT, resume=True)
            report["phases"].append({"name": "same_plan_real_resume", "wall_s": time.perf_counter() - phase_start,
                                      "execution": compact_execution(resumed), "counters": counters(root)})
            rows = {row["id"]: row for row in resumed.get("results", [])}
            _expect(report, "resume_completes_without_duplicate_A",
                    resumed.get("complete") is True and rows.get("stage-a", {}).get("reused") is True
                    and rows.get("stage-b", {}).get("reused") is False
                    and counters(root) == {"stage-a": 1, "stage-b": 1})
            _expect(report, "same_original_plan_and_checkpoint_run",
                    plan == original_plan and resumed.get("plan_sha256") == first.get("plan_sha256")
                    and resumed.get("run_id") == first.get("run_id"))

            (root / "stage-a.txt").write_text("intentionally corrupt local fixture\n", encoding="utf-8")
            stale_review = review_readonly(envelope, root)
            report["phases"].append({"name": "readonly_review_after_A_corruption", **stale_review})
            stale_a = next((item for item in stale_review["review"].get("step_states", [])
                            if item["id"] == "stage-a"), {})
            _expect(report, "corruption_review_requires_reconciliation_without_writes",
                    stale_a.get("state") == "reconciliation_required"
                    and stale_review["review"].get("reconciliation_required") is True
                    and stale_review["checkpoint_bytes_unchanged"]
                    and stale_review["all_project_files_unchanged"] and stale_review["envelope_unchanged"])
            phase_start = time.perf_counter()
            stale = execute_verified(plan, cwd=str(root), confirm=True, timeout=timeout,
                                     checkpoint=CHECKPOINT, resume=True)
            report["phases"].append({"name": "stale_same_plan_resume_no_replay", "wall_s": time.perf_counter() - phase_start,
                                      "execution": compact_execution(stale), "counters": counters(root)})
            rows = {row["id"]: row for row in stale.get("results", [])}
            _expect(report, "stale_resume_never_reexecutes_started_steps",
                    stale.get("complete") is False and rows.get("stage-a", {}).get("status") == "stale"
                    and rows.get("stage-b", {}).get("status") == "stale"
                    and counters(root) == {"stage-a": 1, "stage-b": 1})
            report["active_operations"] = [{"step_id": row["id"], "state": "unknown_requires_reconciliation"}
                                           for row in stale.get("results", [])
                                           if row["status"] in ("running", "uncertain")]
        except (OSError, ValueError, TypeError, KeyError, ImportError, StopIteration) as exc:
            report["failures"].append({"reason": type(exc).__name__, "detail": str(exc)[:2000]})
        _expect(report, "snapshot_sources_after_match", bool(hashes) and sources_match(root, hashes))
        _expect(report, "supervising_sources_after_match", bool(hashes) and sources_match(source_root, hashes))
    report["temporary_project_deleted"] = not root.exists()
    _expect(report, "temporary_project_deleted", report["temporary_project_deleted"])
    _expect(report, "all_five_phases_recorded", len(report["phases"]) == 5)
    report["complete"] = not report["failures"]
    report["decision"] = "fixed_resume_scenario_verified" if report["complete"] else "pilot_not_verified"
    report["total_pilot_wall_s"] = time.perf_counter() - started
    report["usage"]["elapsed_wall_s"] = report["total_pilot_wall_s"]
    report["timing_scope"] = "setup, real commands, read-only reviews, checks and cleanup; excludes serialization and host assessment"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="authorize the fixed temporary-file pilot")
    parser.add_argument("--output", required=True, type=Path, help="new JSON report path; never overwritten")
    parser.add_argument("--timeout", type=int, default=10, choices=range(1, 31))
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("--output must name a new file")
    sys.dont_write_bytecode = True
    source_root = Path(__file__).resolve().parents[1]
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    report = run_pilot(source_root, run=args.run, timeout=args.timeout)
    save_new(args.output, report)
    print(json.dumps({"mode": report["mode"], "complete": report["complete"],
                      "decision": report["decision"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if not args.run or report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
