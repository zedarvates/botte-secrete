"""Compare actual Python and cloud-JavaScript helpers, never a deployed server.

``run_conformance(cloud_root, cases=None, timeout_seconds=10)`` imports the three
explicit local ES modules in Node. The supplied checkout is executable trusted
code, not a sandbox. Inputs, subprocess output and runtime are bounded. The
comparison preserves JSON types and missing/null differences. Assessment ranking
is implementation-specific; its declared exclusions and local safety checks are
reported, rather than pretending that fuzzy and lexical scores are equivalent.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import threading
import time

from skills import __version__
from skills.preflight.assessment import assess_task
from skills.preflight.github_evidence import summarize_github_evidence
from skills.preflight.github_plan import plan_github_research

_HELPERS = {
    "assess_task": (assess_task, "assessment.js", "assessTask", "assessment.py"),
    "plan_github_research": (plan_github_research, "github-plan.js", "planGithubResearch", "github_plan.py"),
    "summarize_github_evidence": (summarize_github_evidence, "github-evidence.js", "summarizeGithubEvidence", "github_evidence.py"),
}
_MAX_CASES = 64
_MAX_INPUT_BYTES = 524288
_MAX_OUTPUT_BYTES = 2097152
_MISSING = object()
_ASSIGNMENT_EXCLUSIONS = [
    "candidate_tools: lexical/fuzzy selection and scores",
    "tool_selection_status: implementation-specific shortlist",
    "context.shortlist_estimated_tokens: implementation-specific shortlist",
    "missing_prerequisites: matching_tool_metadata_within_budget only",
]


def _encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


_PYTHON_IMPORT_HASHES = {
    py: _sha(Path(__file__).with_name(py).read_bytes())
    for _, _, _, py in _HELPERS.values()
}


def _package_version(root):
    try:
        with (root / "package.json").open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) <= 16384:
            value = json.loads(raw).get("version")
            return value if isinstance(value, str) else None
    except (OSError, ValueError, AttributeError):
        pass
    return None


def default_cases() -> list[dict]:
    """A versioned shared corpus, authored examples rather than accuracy claims."""
    tools = [{"name": "github_search_prs", "description": "Search GitHub pull requests"},
             {"name": "run_tests", "description": "Run software tests and assertions"}]
    cases = []
    prompts = ["Retrouver les PR liées à une régression de reconnexion",
               "Find GitHub PRs then run tests", "Ne recherche pas les PR GitHub",
               "Don’t run the tests", 'Lire « tester le jeu »', "Tester le jeu vidéo",
               "Analyser le document café 雪", "Compresser le texte",
               "bonjour", 'Read "unclosed', "Rechercher les PR GitHub"]
    for index, task in enumerate(prompts):
        cases.append({"id": f"assessment-{index + 1}", "helper": "assess_task",
                      "arguments": {"task": task, "available_tools": tools}})
    for name, arguments in [
        ("empty", {"task": ""}),
        ("bool-budget", {"task": "Read", "context_budget": True}),
        ("null-budget", {"task": "Read", "context_budget": None}),
        ("zero-budget", {"task": "Read", "context_budget": 0, "available_tools": tools}),
        ("missing-inventory", {"task": "Lire le document"}),
        ("null-inventory", {"task": "Lire le document", "available_tools": None}),
    ]:
        cases.append({"id": "assessment-" + name, "helper": "assess_task", "arguments": arguments})
    for name, arguments in [
        ("search", {"repository": "owner/repo", "query": "régression café 雪"}),
        ("scope", {"repository": "owner/repo", "query": 'repo:other/repo is:merged "test"'}),
        ("pr", {"repository": "owner/repo", "pr_number": 7}),
        ("null-pr", {"repository": "owner/repo", "pr_number": None}),
        ("invalid-repo", {"repository": "../outside"}),
        ("bool-pr", {"repository": "owner/repo", "pr_number": True}),
        ("null-query", {"repository": "owner/repo", "query": None}),
    ]:
        cases.append({"id": "plan-" + name, "helper": "plan_github_research", "arguments": arguments})
    # JSON has one number type in JS, while Python preserves an integral float.
    cases.append({"id": "plan-integral-float", "helper": "plan_github_research",
                  "arguments": {"repository": "owner/repo", "pr_number": 1.0},
                  "expected_difference": "integral_number_representation"})
    head = "a" * 40
    report = {"repository": "owner/repo", "pull_request": {
        "number": 7, "title": "Régression café 雪", "state": "open", "draft": True,
        "merged": False, "head": {"sha": head},
        "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "owner/repo"}}}}
    variants = [("minimal", report),
                ("explicit-null", {**report, "observed_at": None}),
                ("partial", {**report, "completeness": {"checks": "partial"}, "check_runs": {
                    "total_count": 3, "check_runs": [{"name": "failed", "status": "completed",
                    "conclusion": "failure", "head_sha": "c" * 40,
                    "details_url": "https://example.com/unsafe"}]}}),
                ("bad-number", {**report, "pull_request": {"number": True}}),
                ("bad-date", {**report, "observed_at": "2026-99-99T00:00:00Z"}),
                ("null-files", {**report, "files": None})]
    for name, value in variants:
        cases.append({"id": "summary-" + name, "helper": "summarize_github_evidence",
                      "arguments": {"report_json": json.dumps(value, ensure_ascii=False)}})
    cases.append({"id": "summary-invalid-json", "helper": "summarize_github_evidence",
                  "arguments": {"report_json": "{"}})
    return cases


def _validate_cases(cases, max_cases):
    if isinstance(max_cases, bool) or not isinstance(max_cases, int) or not 1 <= max_cases <= _MAX_CASES:
        raise ValueError("max_cases must be an integer from 1 through 64")
    if not isinstance(cases, list) or not cases or len(cases) > max_cases:
        raise ValueError("cases must be a nonempty bounded list")
    try:
        raw = _encoded(cases)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("cases must contain finite UTF-8 JSON values") from exc
    if len(raw) > _MAX_INPUT_BYTES:
        raise ValueError("case input exceeds 512 KiB")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) - {"id", "helper", "arguments", "expected_difference"}:
            raise ValueError("invalid case envelope")
        name = case.get("id")
        if not isinstance(name, str) or not name or len(name) > 100 or name in ids:
            raise ValueError("case IDs must be unique nonempty strings up to 100 characters")
        ids.add(name)
        if case.get("helper") not in _HELPERS or not isinstance(case.get("arguments"), dict):
            raise ValueError("unsupported helper or nonobject arguments")
        policy = case.get("expected_difference")
        if policy is not None:
            number = case["arguments"].get("pr_number")
            if (policy != "integral_number_representation" or case["helper"] != "plan_github_research"
                    or type(number) is not float or not number.is_integer() or not 1 <= number <= 2147483647):
                raise ValueError("expected difference is restricted to integral Python PR-number floats")
    return copy.deepcopy(cases), raw


def _python_case(case):
    function = _HELPERS[case["helper"]][0]
    try:
        return {"status": "returned", "result": function(**case["arguments"])}
    except (ValueError, TypeError, UnicodeError) as exc:
        return {"status": "rejected", "error_type": type(exc).__name__}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__}


def _node_script() -> str:
    return """import {pathToFileURL} from 'node:url';
import path from 'node:path';
let text=''; for await (const chunk of process.stdin) text+=chunk;
const request=JSON.parse(text), root=process.argv[1];
const mappings={assess_task:['assessment.js','assessTask'],
plan_github_research:['github-plan.js','planGithubResearch'],
summarize_github_evidence:['github-evidence.js','summarizeGithubEvidence']};
const functions={};
for(const [key,[file,name]] of Object.entries(mappings)) {
  const module=await import(pathToFileURL(path.join(root,'src',file)).href);
  if(typeof module[name]!=='function') throw new Error('missing helper export');
  functions[key]=module[name];
}
const results=request.map(test=>{
  try {
    const input=test.arguments;
    const result=functions[test.helper](input);
    if(result===undefined) return {id:test.id,status:'error',error_type:'UndefinedResult'};
    return {id:test.id,status:'returned',result};
  } catch(error) {return {id:test.id,status:error?.name==='Error'?'rejected':'error',error_type:error?.name??'Error'};}
});
process.stdout.write(JSON.stringify({node_version:process.version,results}));
"""


def _node_cases(cloud_root, cases, node_command, timeout_seconds):
    """Drain both streams with hard byte caps; never use a shell."""
    argv = [node_command, "--input-type=module", "-e", _node_script(), str(cloud_root)]
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        return {"status": "not_run", "reason": type(exc).__name__}
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def drain(stream, target, limit):
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if len(target) + len(chunk) > limit:
                overflow.set()
                try:
                    process.kill()
                except OSError:
                    pass
                break
            target.extend(chunk)

    def write():
        try:
            process.stdin.write(_encoded(cases))
            process.stdin.close()
        except (OSError, ValueError):
            pass

    threads = [threading.Thread(target=drain, args=(process.stdout, buffers[0], _MAX_OUTPUT_BYTES), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, buffers[1], 16384), daemon=True),
               threading.Thread(target=write, daemon=True)]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for thread in threads:
        thread.join(timeout=1)
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close()
    if timed_out or overflow.is_set() or process.returncode:
        return {"status": "incomplete", "reason": "timeout" if timed_out else "output_limit" if overflow.is_set() else "node_exit",
                "exit_code": process.returncode}
    try:
        envelope = json.loads(bytes(buffers[0]))
    except (ValueError, UnicodeError):
        return {"status": "incomplete", "reason": "invalid_node_protocol"}
    if (not isinstance(envelope, dict) or set(envelope) != {"node_version", "results"}
            or not isinstance(envelope["node_version"], str) or not isinstance(envelope["results"], list)
            or len(envelope["results"]) != len(cases)):
        return {"status": "incomplete", "reason": "invalid_node_protocol"}
    for case, result in zip(cases, envelope["results"]):
        if (not isinstance(result, dict) or result.get("id") != case["id"]
                or result.get("status") not in {"returned", "rejected", "error"}
                or (result["status"] == "returned" and "result" not in result)):
            return {"status": "incomplete", "reason": "invalid_node_protocol"}
    return {"status": "completed", **envelope}


def _project(helper, value):
    value = copy.deepcopy(value)
    if not isinstance(value, dict):
        return value
    if helper == "assess_task":
        value.pop("candidate_tools", None)
        value.pop("tool_selection_status", None)
        if isinstance(value.get("context"), dict):
            value["context"].pop("shortlist_estimated_tokens", None)
        if isinstance(value.get("missing_prerequisites"), list):
            value["missing_prerequisites"] = [x for x in value["missing_prerequisites"]
                                                if x != "matching_tool_metadata_within_budget"]
    elif helper == "summarize_github_evidence" and isinstance(value.get("measurements"), dict):
        value["measurements"].pop("output_utf8_bytes", None)
    return value


def _differences(left, right, path="$", *, limit=32):
    """Typed structural differences: False != 0 and absent != explicit null."""
    result = []

    def visit(a, b, at):
        if len(result) >= limit:
            return
        if a is _MISSING or b is _MISSING:
            result.append({"path": at, "kind": "missing", "python_present": a is not _MISSING,
                           "cloud_present": b is not _MISSING})
        elif type(a) is not type(b):
            result.append({"path": at, "kind": "type", "python_type": type(a).__name__, "cloud_type": type(b).__name__})
        elif isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                visit(a.get(key, _MISSING), b.get(key, _MISSING), at + "/" + str(key).replace("~", "~0").replace("/", "~1"))
        elif isinstance(a, list):
            if len(a) != len(b):
                result.append({"path": at, "kind": "length", "python_length": len(a), "cloud_length": len(b)})
            for index, (x, y) in enumerate(zip(a, b)):
                visit(x, y, at + "/" + str(index))
        elif a != b:
            # Raw values are already retained in each bounded projected result.
            result.append({"path": at, "kind": "value"})
    visit(left, right, path)
    return result


def _assessment_invariants(result, arguments):
    if not isinstance(result, dict):
        return ["assessment_result_not_object"]
    tools = result.get("candidate_tools")
    offered = arguments.get("available_tools") or []
    names = {x.get("name") for x in offered if isinstance(x, dict)}
    if (not isinstance(tools, list) or len(tools) > 5 or any(
            not isinstance(x, dict) or x.get("name") not in names or x.get("capability_verified") is not False
            for x in tools)):
        return ["shortlist_not_bounded_supplied_unverified_tools"]
    if len({x["name"] for x in tools}) != len(tools):
        return ["shortlist_contains_duplicate_tools"]
    if any(type(x.get("lexical_score")) not in (int, float)
           or not 0 <= x["lexical_score"] <= 1 or not math.isfinite(x["lexical_score"]) for x in tools):
        return ["shortlist_score_is_not_finite_number_in_range"]
    if result.get("tool_selection_status") != ("proposed" if tools else "abstained"):
        return ["shortlist_status_inconsistent"]
    context = result.get("context", {})
    used = context.get("shortlist_estimated_tokens") if isinstance(context, dict) else None
    budget = arguments.get("context_budget", 2000)
    if type(used) is not int or not 0 <= used <= budget:
        return ["shortlist_budget_not_respected"]
    metadata = {x["name"]: x for x in offered if isinstance(x, dict)}
    expected_used = sum(max(1, (len(x["name"]) + len(metadata[x["name"]].get("description", "")) + 3) // 4)
                        for x in tools)
    if used != expected_used:
        return ["shortlist_metadata_estimate_inconsistent"]
    return []


def run_conformance(cloud_root, cases=None, *, node_command="node", timeout_seconds=10, max_cases=64) -> dict:
    """Compare trusted local helpers; an unavailable runtime cannot pass.

    Explicit cases use ``{id, helper, arguments}``. Only the predeclared integral
    PR-number float representation difference can be marked expected. Error
    messages/classes may differ between languages; acceptance/rejection may not.
    """
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 120 or not math.isfinite(timeout_seconds):
        raise ValueError("timeout_seconds must be finite and within (0,120]")
    if not isinstance(node_command, str) or not node_command or "\x00" in node_command:
        raise ValueError("node_command must be one executable name or path")
    cases, raw = _validate_cases(default_cases() if cases is None else cases, max_cases)
    root = Path(cloud_root).resolve()
    source_files = []
    for _, js, _, py in _HELPERS.values():
        path = root / "src" / js
        if not path.is_file() or not path.resolve().is_relative_to(root):
            return {"schema": "parcimonia.conformance/v1", "status": "not_run", "passed": False,
                    "reason": "missing_or_external_cloud_source", "source": js, "results": []}
        source_files.append({"helper_source": js, "cloud_sha256": _sha(path.read_bytes()),
                             "python_source": py, "python_sha256": _sha(Path(__file__).with_name(py).read_bytes())})
    report = {"schema": "parcimonia.conformance/v1", "status": "incomplete", "passed": False,
              "scope": "local_source_helpers_not_deployed_service_or_mcp_wrappers",
              "python_version": platform.python_version(), "python_package_version": __version__,
              "cloud_package_version": _package_version(root), "source_files": source_files,
              "case_input_sha256": _sha(raw), "case_count": len(cases), "results": [],
              "not_covered": [{"helper": "compute_statistics", "reason": "separate_engine_not_in_this_shared_helper_contract"}],
              "projection_exclusions": {"assess_task": _ASSIGNMENT_EXCLUSIONS,
                                        "summarize_github_evidence": ["measurements.output_utf8_bytes: serialization size retained separately"]},
              "difference_inventory": "first_32_paths_per_case_not_exhaustive",
              "exception_comparison": "acceptance_and_exception_category_not_message_or_validation_correctness",
              "budgets": {"max_cases": max_cases, "max_input_bytes": _MAX_INPUT_BYTES,
                          "max_cloud_output_bytes": _MAX_OUTPUT_BYTES, "node_timeout_seconds": timeout_seconds},
              "boundaries": {"network_requested": False, "model_calls": 0, "sandbox": False,
                             "trusted_local_module_execution": True}}
    if any(row["python_sha256"] != _PYTHON_IMPORT_HASHES[row["python_source"]] for row in source_files):
        report.update(status="not_run", reason="python_source_changed_since_import")
        return report
    if shutil.which(node_command) is None:
        report.update(status="not_run", reason="node_unavailable")
        return report
    started = time.monotonic()
    cloud = _node_cases(root, cases, node_command, timeout_seconds)
    report["cloud_execution"] = {key: value for key, value in cloud.items() if key != "results"}
    if cloud["status"] != "completed":
        report.update(status=cloud["status"], reason=cloud.get("reason"))
        return report
    for case, cloud_result in zip(cases, cloud["results"]):
        py = _python_case(case)
        row = {"id": case["id"], "helper": case["helper"], "input_sha256": _sha(_encoded(case["arguments"])),
               "python": py, "cloud": {k: v for k, v in cloud_result.items() if k != "id"}, "differences": [],
               "input": case["arguments"]}
        if py["status"] == "error" or cloud_result["status"] == "error":
            row["status"] = "incomplete"
        elif py["status"] != cloud_result["status"]:
            expected = (case.get("expected_difference") == "integral_number_representation"
                        and py["status"] == "rejected" and cloud_result["status"] == "returned")
            # The known input representation boundary excuses only acceptance,
            # never an arbitrary cloud result for that case.
            if expected:
                normalized = copy.deepcopy(case)
                normalized["arguments"]["pr_number"] = int(normalized["arguments"]["pr_number"])
                reference = _python_case(normalized)
                row["normalized_python_reference"] = reference
                expected = (reference["status"] == "returned" and not _differences(
                    _project(case["helper"], reference["result"]),
                    _project(case["helper"], cloud_result["result"])))
            row["status"] = "known_difference" if expected else "mismatch"
            row["differences"] = [{"path": "$", "kind": "acceptance"}]
            if expected:
                row["expected_difference"] = case["expected_difference"]
        elif py["status"] == "rejected":
            row["status"] = "matched_rejection"
        else:
            p, c = py["result"], cloud_result["result"]
            row["differences"] = _differences(_project(case["helper"], p), _project(case["helper"], c))
            invariants = {}
            if case["helper"] == "assess_task":
                invariants = {"python": _assessment_invariants(p, case["arguments"]),
                              "cloud": _assessment_invariants(c, case["arguments"])}
                row["invariant_failures"] = invariants
            row["status"] = "mismatch" if row["differences"] or any(invariants.values()) else "matched"
        report["results"].append(row)
    counts = {name: sum(row["status"] == name for row in report["results"])
              for name in ("matched", "matched_rejection", "known_difference", "mismatch", "incomplete")}
    report["counts"] = counts
    report["passed"] = not counts["mismatch"] and not counts["incomplete"]
    report["status"] = "failed" if counts["mismatch"] else "incomplete" if counts["incomplete"] else "passed_with_known_differences" if counts["known_difference"] else "passed"
    report["elapsed_seconds"] = round(time.monotonic() - started, 6)
    try:
        unchanged = all(
            _sha((root / "src" / row["helper_source"]).read_bytes()) == row["cloud_sha256"]
            and _sha(Path(__file__).with_name(row["python_source"]).read_bytes()) == row["python_sha256"]
            for row in source_files)
    except OSError:
        unchanged = False
    report["source_unchanged_after_comparison"] = unchanged
    if not unchanged:
        report.update(status="incomplete", passed=False, reason="source_changed_during_comparison")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-root", required=True, type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    try:
        cases = None
        if args.cases:
            with args.cases.open("rb") as stream:
                raw = stream.read(_MAX_INPUT_BYTES + 1)
            if len(raw) > _MAX_INPUT_BYTES:
                raise ValueError("case input exceeds 512 KiB")
            cases = json.loads(raw)
        report = run_conformance(args.cloud_root, cases, node_command=args.node, timeout_seconds=args.timeout)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if report["passed"] else 1 if report["status"] == "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
