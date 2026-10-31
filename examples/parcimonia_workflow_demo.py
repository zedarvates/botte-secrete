"""Replay authored Parcimonia examples without executing tools or using a model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills import __version__
from skills.preflight.assessment import assess_task
from skills.preflight.github_plan import plan_github_research
from skills.preflight.github_evidence import summarize_github_evidence


# Illustrative metadata, not an inventory of verified connected tools.
OFFERED_TOOLS = [
    {"name": "github_search_prs", "description": "Search GitHub pull requests by repository"},
    {"name": "github_read_pr", "description": "Read GitHub PR metadata, files and checks"},
    {"name": "run_tests", "description": "Run software regression tests with assertions"},
    {"name": "capture_game_state", "description": "Capture game observations for a playtest"},
    {"name": "apply_game_input", "description": "Apply bounded gameplay inputs"},
]
CASES = [
    ("github-fr", "Rechercher les PR GitHub de Botte Secrète", "proposed", "github_research"),
    ("software-en", "Run regression tests", "proposed", "software_testing"),
    ("game-fr", "Tester le jeu vidéo", "proposed", "game_playtest"),
    ("ambiguous-en", "Fix code and translate the document", "abstained", None),
    ("negated-en", "Don’t run tests", "abstained", None),
]


def measured_call(function, *args, **kwargs) -> dict:
    """Measure this synchronous helper only, excluding encoding and host work."""
    started = perf_counter_ns()
    result = function(*args, **kwargs)
    elapsed = perf_counter_ns() - started
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"result": result, "measurement": {"helper_wall_ns": elapsed,
            "result_utf8_bytes": len(encoded), "scope": "one_helper_call_only"}}


def replay() -> dict:
    cases = []
    for case_id, task, expected_status, expected_intent in CASES:
        observed = measured_call(assess_task, task, OFFERED_TOOLS, context_budget=1200)
        result = observed["result"]
        if (result["status"], result["intent"]) != (expected_status, expected_intent):
            raise RuntimeError(f"Authored fixture changed: {case_id}")
        cases.append({"id": case_id, "task": task, **observed})
    plans = {
        "search": measured_call(plan_github_research, "zedarvates/botte-secrete", "Parcimonia"),
        "pull_request": measured_call(plan_github_research, "zedarvates/botte-secrete", pr_number=147),
    }
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        "skills/preflight/assessment.py", "skills/preflight/github_plan.py",
        "skills/preflight/github_evidence.py")}
    return {
        "schema": "parcimonia.workflow-demo/v1", "runtime_version": __version__,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0], "source_sha256": source_hashes,
        "origin": "authored_demonstration_not_a_quality_or_savings_benchmark",
        "inventory_origin": "illustrative_metadata_not_verified_connected_tools",
        "cases": cases, "github_plans": plans,
        "fixture_checks": {"count": len(CASES), "passed": True},
        "execution": {"tools_executed": 0, "network_calls": 0, "model_calls": 0},
        "host_measurements": {"provider_tokens": None, "cost": None,
                              "end_to_end_latency_ms": None, "savings": None},
        "measurement_limit": "Helper timing and UTF-8 size do not establish task speed, billed tokens or savings.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, metavar="ABSOLUTE_DIRECTORY",
                        help="Create a report outside the repository; existing files are never overwritten.")
    parser.add_argument("--github-report", type=Path, metavar="JSON_FILE",
                        help="Also summarize a supplied GitHub observation, without fetching or verifying it.")
    args = parser.parse_args()
    output = None
    if args.out is not None:
        if not args.out.is_absolute() or args.out.resolve().is_relative_to(ROOT.resolve()):
            parser.error("--out must be an absolute directory outside the repository")
        output = args.out.resolve() / "parcimonia-workflow.json"
        if output.exists():
            parser.error("report already exists; choose a new output directory")
    report = replay()
    if args.github_report is not None:
        with args.github_report.open("rb") as stream:
            source = stream.read(131_073)
        if len(source) > 131_072:
            parser.error("--github-report exceeds 128 KiB")
        observed = measured_call(summarize_github_evidence, source.decode("utf-8"))
        report["github_observation"] = {
            "origin": "caller_supplied_observation_separate_from_authored_examples",
            "input_sha256": hashlib.sha256(source).hexdigest(), **observed}
    print("PARCIMONIA | reproducible development demonstration")
    print("Illustrative tool metadata; helper calls only. No tools, GitHub reads or games are executed.")
    for case in report["cases"]:
        result = case["result"]
        candidates = ", ".join(tool["name"] for tool in result["candidate_tools"]) or "none"
        print(f"\n{case['id']}: {case['task']}")
        print(f"  {result['status']} | {result['intent'] or 'host review'} | candidates: {candidates}")
        if result["missing_prerequisites"]:
            print("  Missing: " + ", ".join(result["missing_prerequisites"]))
    search = report["github_plans"]["search"]["result"]["search"]
    print("\nGitHub search plan: " + search["query"])
    print("PR plan: metadata -> filenames -> selected patches -> exact-head checks -> head/base refresh")
    print(f"Authored fixture checks: {len(CASES)}/{len(CASES)} passed. These are examples, not benchmark accuracy.")
    print("Helper timings and UTF-8 sizes are recorded separately. Provider usage and savings are unknown.")
    if "github_observation" in report:
        summary = report["github_observation"]["result"]
        sizes = summary["measurements"]
        print(f"\nSupplied GitHub observation: {sizes['input_utf8_bytes']} -> {sizes['output_utf8_bytes']} UTF-8 bytes")
        print("Check counts: " + json.dumps(summary["checks"]["counts"], sort_keys=True))
        print("Caller-supplied data remains unverified; byte sizes are not billed tokens.")
    if output is not None:
        data = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if len(data.encode("utf-8")) > 64 * 1024:
            raise RuntimeError("Demo report exceeded its 64 KiB bound")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(data)
        print("Report: " + str(output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Demo failed: {error}", file=sys.stderr)
        raise SystemExit(1)
