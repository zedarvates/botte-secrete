"""Preview or explicitly run a fixed, isolated shared-prerequisite demonstration.

``python -m scripts.plan_synergy_pilot --run --output <new-report.json>``
uses the existing Conductor executor in temporary projects only. This script
supplies fixed trusted commands; the synergy analyser generates no commands.
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

SCHEMA = "parcimonia.plan-synergy-pilot/v1"
SOURCE_FILES = (
    "skills/__init__.py", "skills/atomic_json.py",
    "skills/capabilities/__init__.py", "skills/capabilities/registry.py",
    "skills/conductor/__init__.py", "skills/conductor/conductor.py",
    "skills/conductor/executor.py", "skills/conductor/verified.py",
    "skills/conductor/preferences.py", "skills/conductor/selection.py",
    "skills/conductor/handoff.py", "skills/conductor/uncertainty.py",
    "skills/conductor/synergies.py", "scripts/plan_synergy_pilot.py",
)
INPUT_TEXT = '{"rows":[{"id":"charlie","value":5},{"id":"alpha","value":3},{"id":"bravo","value":4}]}\n'
NORMALIZED = {"rows": [{"id": "alpha", "value": 3}, {"id": "bravo", "value": 4},
                       {"id": "charlie", "value": 5}]}
EXPECTED = {"summary.json": {"count": 3, "total": 12},
            "index.json": {"ids": ["alpha", "bravo", "charlie"]}}
PREPARES = {"prep-a": "prepared-a.json", "prep-b": "prepared-b.json",
            "prep-shared": "prepared-shared.json"}
CONSUMERS = {"summary-separate": ("prep-a", "summary.json", "a"),
             "index-separate": ("prep-b", "index.json", "b"),
             "summary-shared": ("prep-shared", "summary.json", "a"),
             "index-shared": ("prep-shared", "index.json", "b")}
METHODS = {"separate": ["prep-a", "summary-separate", "prep-b", "index-separate"],
           "shared": ["prep-shared", "summary-shared", "index-shared"]}
WORKER = '''"""Fixed pilot worker; no services, network, models or production paths."""
import json
import sys
from pathlib import Path

prepares = {"prep-a": "prepared-a.json", "prep-b": "prepared-b.json", "prep-shared": "prepared-shared.json"}
consumers = {"summary-separate": ("prep-a", "summary.json"), "index-separate": ("prep-b", "index.json"),
             "summary-shared": ("prep-shared", "summary.json"), "index-shared": ("prep-shared", "index.json")}
stage = sys.argv[1]
if stage not in prepares and stage not in consumers:
    raise SystemExit("unknown fixed pilot stage")
if stage in prepares:
    rows = json.loads(Path("input.json").read_text(encoding="utf-8"))["rows"]
    result = {"rows": sorted(rows, key=lambda row: row["id"])}
    target = prepares[stage]
else:
    preparation, target = consumers[stage]
    rows = json.loads(Path(prepares[preparation]).read_text(encoding="utf-8"))["rows"]
    result = {"count": len(rows), "total": sum(row["value"] for row in rows)} if target == "summary.json" else {"ids": [row["id"] for row in rows]}
counter = Path(stage + "-counter.json")
count = json.loads(counter.read_text(encoding="utf-8"))["count"] if counter.exists() else 0
counter.write_text(json.dumps({"count": count + 1}, sort_keys=True, separators=(",", ":")) + "\\n", encoding="utf-8")
Path(target).write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\\n", encoding="utf-8")
'''
LIMITATIONS = [
    "One fixed local correctness demonstration; equality of these outputs does not qualify arbitrary shared work.",
    "The shared operation and full candidate plans are explicitly supplied, not inferred from similar names or commands.",
    "Planning costs are synthetic estimates; observed preparation counts are separate execution evidence.",
    "Two preparations versus one is specific to this fixture; no general time, token, money, energy or quality gain is established.",
    "Observed wall time includes setup and checks; it is not a representative performance benchmark.",
    "Source/checkpoint hashes establish content consistency, not authenticity or user authority.",
    "The analyser grants no selection or execution authority; --run and existing Conductor confirmation cover only this fixed pilot.",
    "Temporary projects and checkpoints are deleted; no production, network, model or robot resources are invoked.",
]


def payload(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(payload(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return payload(value) + b"\n"


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def source_hashes(root):
    return {name: file_hash(root / name) for name in SOURCE_FILES}


def sources_match(root, hashes):
    try:
        return bool(hashes) and all(file_hash(root / name) == sha for name, sha in hashes.items())
    except OSError:
        return False


def snapshot_sources(source_root, root, hashes):
    for name, sha in hashes.items():
        data = (source_root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("source changed before snapshot")
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def build_envelope():
    from skills.conductor.preferences import METRICS

    actions = []
    for aid in [*PREPARES, *CONSUMERS]:
        needs = [] if aid in PREPARES else [CONSUMERS[aid][0]]
        projects = ["a", "b"] if aid == "prep-shared" else ["a" if aid == "prep-a" else "b"] if aid in PREPARES else [CONSUMERS[aid][2]]
        actions.append({"id": aid, "needs": needs, "projects": projects,
                        "metrics": {metric: 1 if metric == "elapsed_minutes" else None for metric in METRICS},
                        "provenance": {"kind": "estimate", "ref": "synthetic-fixed-pilot-not-measured-cost"}})
    comparison = {"schema": "parcimonia.plan-preferences/v1", "currency": "EUR",
                  "projects": [{"id": "a", "goals": ["summary"]}, {"id": "b", "goals": ["index"]}],
                  "actions": actions,
                  "candidates": [{"id": cid, "steps": list(steps), "goals": {"a": ["summary"], "b": ["index"]}}
                                 for cid, steps in METHODS.items()],
                  "preferences": {"priorities": [{"metric": "elapsed_minutes"}]}}
    return {"schema": "parcimonia.plan-synergies/v1", "comparison_request": comparison,
            "opportunities": [{"id": "same-input-preparation", "baseline_candidate_id": "separate",
                               "shared_candidate_id": "shared", "separate_action_ids": ["prep-a", "prep-b"],
                               "shared_action_id": "prep-shared",
                               "assumption_ref": "fixed-same-input-normalization-and-independently-verified-consumers"}]}


def _sha_check(path, data):
    return {"kind": "file_sha256", "path": path,
            "value": hashlib.sha256(data).hexdigest()}


def build_project(root, hashes, candidate_id):
    """Create only the fixed fixture and supply trusted commands/checks."""
    if candidate_id not in METHODS:
        raise ValueError("unknown fixed pilot candidate")
    (root / "worker.py").write_text(WORKER, encoding="utf-8")
    (root / "input.json").write_text(INPUT_TEXT, encoding="utf-8")
    bindings = {**hashes, "worker.py": file_hash(root / "worker.py"),
                "input.json": file_hash(root / "input.json")}
    steps = []
    for aid in METHODS[candidate_id]:
        preparing = aid in PREPARES
        target = PREPARES[aid] if preparing else CONSUMERS[aid][1]
        expected = NORMALIZED if preparing else EXPECTED[target]
        requires = [_sha_check("input.json", INPUT_TEXT.encode("utf-8"))] if preparing else [
            _sha_check(PREPARES[CONSUMERS[aid][0]], encoded(NORMALIZED))]
        counter = aid + "-counter.json"
        steps.append({"id": aid, "capability": "plan-synergy-pilot", "local": True,
                      "command": f"python -B worker.py {aid}",
                      "needs": [] if preparing else [CONSUMERS[aid][0]],
                      "requires": requires,
                      "ensures": [_sha_check(target, encoded(expected)), _sha_check(counter, encoded({"count": 1}))],
                      "observes": [target, counter], "source_hashes": dict(bindings)})
    return {"schema": "botte.skill-plan/v1", "goal": "Verify the same fixed summary and index",
            "context": "isolated-shared-prerequisite-v1", "steps": steps}


def counters(root):
    counts = {}
    for aid in [*PREPARES, *CONSUMERS]:
        path = root / (aid + "-counter.json")
        value = json.loads(path.read_text(encoding="utf-8"))["count"] if path.exists() else 0
        counts[aid] = value if type(value) is int else None
    return counts


def compact_execution(report):
    result = {key: report[key] for key in ("schema", "run_id", "plan_sha256", "context_sha256",
                                         "mode", "complete", "summary", "coverage", "child_cost", "error")
              if key in report}
    result["full_report_sha256"] = digest(report)
    result["results"] = []
    for row in report.get("results", []):
        kept = {key: row[key] for key in ("id", "status", "started", "reused", "exit_code", "duration_s",
                                        "note", "changed_paths", "dependencies", "output_sha256", "output_bytes") if key in row}
        for group in ("source_checks", "source_checks_after", "precondition_checks", "postcondition_checks"):
            checks = row.get(group, [])
            kept[group] = {"count": len(checks), "all_passed": all(check["passed"] for check in checks),
                           "failed": [check for check in checks if not check["passed"]]}
        result["results"].append(kept)
    return result


def compact_plan(plan):
    return {**{key: plan[key] for key in ("schema", "goal", "context")},
            "full_plan_sha256": digest(plan),
            "steps": [{**{key: value for key, value in step.items() if key != "source_hashes"},
                       "source_hashes_sha256": digest(step["source_hashes"]),
                       "source_binding_count": len(step["source_hashes"])} for step in plan["steps"]]}


def _expect(report, label, condition):
    report["checks"][label] = bool(condition)
    if not condition:
        report["failures"].append({"check": label, "reason": "expected_local_evidence_not_verified"})


def run_pilot(source_root, *, run=False, timeout=10):
    if type(run) is not bool or type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError("run must be a boolean and timeout an integer from 1 to 30")
    started = time.perf_counter()
    source_root = Path(source_root).resolve()
    report = {"schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": "execution" if run else "preview", "complete": False,
              "environment": {"python": sys.version, "platform": sys.platform},
              "authorization_scope": "--run permits only this fixed temporary-file pilot; Conductor confirm=true is still required.",
              "source_hashes": {}, "worker_sha256": hashlib.sha256(WORKER.encode("utf-8")).hexdigest(),
              "input_sha256": hashlib.sha256(INPUT_TEXT.encode("utf-8")).hexdigest(),
              "expected_outputs": {name: {"value": value, "sha256": hashlib.sha256(encoded(value)).hexdigest()}
                                   for name, value in EXPECTED.items()},
              "cases": [{"candidate_id": cid, "status": "not_executed"} for cid in METHODS],
              "checks": {}, "failures": [], "active_operations": [],
              "usage": {"elapsed_wall_s": None, "tokens": None, "money": None, "energy_wh": None,
                        "peak_ram_gib": None, "human_minutes": None},
              "gain_claim": None, "limitations": list(LIMITATIONS)}
    if not run:
        report["decision"] = "preview_only_no_execution_evidence"
        report["total_pilot_wall_s"] = time.perf_counter() - started
        return report

    hashes, outputs = {}, {}
    with tempfile.TemporaryDirectory(prefix="botte-synergy-pilot-") as temporary:
        workspace = Path(temporary)
        try:
            hashes = source_hashes(source_root)
            report["source_hashes"] = hashes
            from skills.conductor.handoff import prepare_plan_handoff
            from skills.conductor.preferences import propose_plans
            from skills.conductor.selection import select_plan
            from skills.conductor.synergies import analyse_plan_synergies
            from skills.conductor.verified import execute_verified

            functions = ((prepare_plan_handoff, "handoff.py"), (select_plan, "selection.py"),
                         (analyse_plan_synergies, "synergies.py"), (execute_verified, "verified.py"))
            bound = all(Path(function.__code__.co_filename).resolve() == source_root / "skills/conductor" / name
                        for function, name in functions)
            _expect(report, "supervising_sources_before_match", bound and sources_match(source_root, hashes))
            if not report["checks"]["supervising_sources_before_match"]:
                raise ValueError("supervising source binding not satisfied")
            envelope = build_envelope()
            before = deepcopy(envelope)
            analysis = analyse_plan_synergies(envelope)
            report["planning_input"] = envelope
            report["synergy_analysis"] = analysis
            _expect(report, "analysis_preserves_input_and_nonselection", envelope == before
                    and analysis["selected_candidate_id"] is None)
            _expect(report, "declared_opportunity_compared", analysis["opportunities"][0]["status"] == "compared")
            comparison = envelope["comparison_request"]
            comparison_digest = propose_plans(comparison)["input_digest"]
            report["comparison_input_digest"] = comparison_digest
            for case in report["cases"]:
                cid = case["candidate_id"]
                root = workspace / cid
                root.mkdir()
                try:
                    snapshot_sources(source_root, root, hashes)
                    plan = build_project(root, hashes, cid)
                    receipt = select_plan(comparison, cid, comparison_digest)
                    handoff = prepare_plan_handoff(comparison, receipt, plan)
                    case.update(plan=compact_plan(plan), handoff_id=handoff["handoff_id"],
                                handoff_input_digest=handoff["input_digest"],
                                handoff_execution_authorized=handoff["execution_authorized"])
                    original_plan = deepcopy(plan)
                    _expect(report, cid + "_sources_before_match", sources_match(root, hashes)
                            and sources_match(source_root, hashes))
                    if not report["checks"][cid + "_sources_before_match"]:
                        raise ValueError("source binding not satisfied before execution")
                    phase_start = time.perf_counter()
                    execution = execute_verified(handoff["execution_plan"], cwd=str(root), confirm=True,
                                                 timeout=timeout, checkpoint="work/checkpoint.json")
                    case.update(status="executed", wall_s=time.perf_counter() - phase_start,
                                execution=compact_execution(execution), counters=counters(root),
                                checkpoint_sha256=file_hash(root / "work/checkpoint.json"))
                    actual = {name: (root / name).read_bytes() for name in EXPECTED if (root / name).is_file()}
                    outputs[cid] = actual
                    case["output_sha256"] = {name: hashlib.sha256(data).hexdigest() for name, data in actual.items()}
                    _expect(report, cid + "_verified_exact_outputs", execution["complete"] is True
                            and actual == {name: encoded(value) for name, value in EXPECTED.items()})
                    _expect(report, cid + "_supplied_plan_and_handoff_preserved", plan == original_plan
                            and handoff["input_digest"] == comparison_digest
                            and handoff["execution_plan_sha256"] == execution["plan_sha256"])
                    expected_counts = {aid: int(aid in METHODS[cid]) for aid in [*PREPARES, *CONSUMERS]}
                    _expect(report, cid + "_each_expected_stage_once", case["counters"] == expected_counts)
                    case["preparation_count"] = sum(case["counters"][aid] for aid in PREPARES)
                    _expect(report, cid + "_snapshot_sources_after_match", sources_match(root, hashes))
                    report["active_operations"].extend({"candidate_id": cid, "step_id": row["id"], "state": row["status"]}
                                                        for row in execution["results"] if row["status"] in ("running", "uncertain"))
                except Exception as exc:
                    case["status"] = "failed"
                    report["failures"].append({"candidate_id": cid, "reason": type(exc).__name__, "detail": str(exc)[:2000]})
            _expect(report, "same_expected_terminal_outputs_between_cases", set(outputs) == set(METHODS)
                    and outputs["separate"] == outputs["shared"])
            counts = {case["candidate_id"]: case.get("preparation_count") for case in report["cases"]}
            _expect(report, "observed_fixed_preparations_two_versus_one", counts == {"separate": 2, "shared": 1})
            _expect(report, "planning_input_preserved_after_execution", envelope == before)
        except Exception as exc:
            report["failures"].append({"phase": "setup_or_comparison", "reason": type(exc).__name__, "detail": str(exc)[:2000]})
        _expect(report, "supervising_sources_after_match", sources_match(source_root, hashes))
    report["temporary_projects_deleted"] = not workspace.exists()
    _expect(report, "temporary_projects_deleted", report["temporary_projects_deleted"])
    _expect(report, "both_cases_executed", all(case["status"] == "executed" for case in report["cases"]))
    report["complete"] = not report["failures"]
    report["decision"] = "fixed_shared_prerequisite_verified" if report["complete"] else "pilot_not_verified"
    report["total_pilot_wall_s"] = time.perf_counter() - started
    report["usage"]["elapsed_wall_s"] = report["total_pilot_wall_s"]
    report["timing_scope"] = "setup, source snapshots, planning/choice/handoff, real commands, checks and cleanup; excludes serialization and host assessment"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="authorize the fixed temporary-file pilot")
    parser.add_argument("--output", required=True, type=Path, help="new JSON report file; never overwritten")
    parser.add_argument("--timeout", type=int, default=10, choices=range(1, 31))
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("--output must name a new file")
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    report = run_pilot(root, run=args.run, timeout=args.timeout)
    save_new(args.output, report)
    print(json.dumps({"mode": report["mode"], "complete": report["complete"],
                      "decision": report["decision"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if not args.run or report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
