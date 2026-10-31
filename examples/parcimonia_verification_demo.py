"""Execute six bounded, authored verification examples through the workbench.

    python examples/parcimonia_verification_demo.py --out /absolute/new-directory \
        --cloud-root /explicit/trusted/botte-cloud-checkout

The fixtures are deliberately authored examples, not user bugs or a task-speed
benchmark. The explorer traverses actual loopback HTTP HTML; it does not operate
a graphical browser. The optional cloud checkout is executable trusted code.
No output directory is reused and no model or deployed service is called.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills import __version__
from skills.app_test.prioritization import append_observations, command_fingerprint
from skills.app_test.process_oracle import invoke_json


SOURCE_FILES = (
    "examples/parcimonia_verification_demo.py", "skills/app_test/workbench.py",
    "skills/app_test/reducer.py", "skills/app_test/prioritization.py",
    "skills/app_test/mutation.py", "skills/app_test/explorer.py",
    "skills/app_test/flaky.py", "skills/app_test/process_oracle.py",
    "skills/preflight/conformance.py", "skills/preflight/assessment.py",
    "skills/preflight/github_plan.py", "skills/preflight/github_evidence.py",
)

ORACLE = '''import json, sys
payload = json.load(sys.stdin)
if sys.argv[1] == "reduce":
    failed = "CONNECT" in payload and "CLOSE" in payload and payload.index("CONNECT") < payload.index("CLOSE")
    result = {"status": "failed" if failed else "passed"}
    if failed:
        result["failure_fingerprint"] = "authored.connect-before-close.v1"
else:
    failed = payload["attempt"] % 2 == 0
    result = {"status": "failed" if failed else "passed",
              "failure_signature": "authored.alternating-exit.v1" if failed else None,
              "context_sha256": payload["context_sha256"]}
print(json.dumps(result))
'''

CHECK = '''import json, sys, time
label = sys.argv[1]
if label == "slow-pass":
    time.sleep(0.02)
    passed = sum([1, 2, 3]) == 6
elif label == "fast-failure":
    passed = sum([1, 2, 3]) == 7  # Deliberately wrong authored expectation.
else:
    passed = sorted([3, 1, 2]) == [1, 2, 3]
print(json.dumps({"status": "passed" if passed else "failed",
                  "fixture": label}))
'''


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, text: str) -> Path:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
    return path


def _json_file(path: Path, value) -> Path:
    return _write(path, json.dumps(value, ensure_ascii=True, allow_nan=False,
                                  indent=2) + "\n")


def _sources() -> list[dict]:
    return [{"path": name, "sha256": _sha((ROOT / name).read_bytes())}
            for name in SOURCE_FILES]


def _revision() -> dict:
    result = {}
    for key, args in (("head", ["git", "rev-parse", "HEAD"]),
                      ("tracked_diff_sha256", ["git", "diff", "--binary", "HEAD"])):
        proc = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=5,
                              check=False)
        result[key] = (proc.stdout.decode("ascii").strip() if key == "head"
                       else _sha(proc.stdout)) if proc.returncode == 0 else None
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, timeout=5, check=False)
    result["worktree_clean"] = not status.stdout if status.returncode == 0 else None
    return result


class Demonstration:
    def __init__(self, output: Path):
        self.output = output
        self.commands: list[dict] = []
        self.fixtures: list[dict] = []

    def text(self, relative: str, text: str) -> Path:
        path = self.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, text)
        self.fixtures.append({"path": relative, "sha256": _sha(path.read_bytes())})
        return path

    def data(self, relative: str, value) -> Path:
        return self.text(relative, json.dumps(value, ensure_ascii=True, allow_nan=False,
                                               indent=2) + "\n")

    def cli(self, operation: str, *arguments: str, timeout: float = 60) -> tuple[dict, int]:
        argv = [sys.executable, "-m", "skills.app_test.workbench", operation,
                *map(str, arguments)]
        started = time.monotonic()
        command = {"argv": argv, "cwd": str(ROOT), "status": "started"}
        self.commands.append(command)
        try:
            proc = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout,
                                  check=False)
        except subprocess.TimeoutExpired:
            command.update(status="timeout", exit=None,
                           elapsed_ms=round((time.monotonic() - started) * 1000, 3))
            raise
        command.update(status="exited", exit=proc.returncode,
                       elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                       stdout_sha256=_sha(proc.stdout), stderr_sha256=_sha(proc.stderr))
        if len(proc.stdout) > 1024 * 1024 or len(proc.stderr) > 128 * 1024:
            raise RuntimeError("authored demo command exceeded its output limit")
        result = json.loads(proc.stdout.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("workbench did not return one JSON object")
        return result, proc.returncode

    def reduction(self) -> dict:
        oracle = self.text("reducer_oracle.py", ORACLE)
        command = self.data("reduce-command.json", [sys.executable, "-I", str(oracle), "reduce"])
        initial = ["irrelevant-a", "CONNECT", "irrelevant-b", "CLOSE", "irrelevant-c"]
        source = self.data("reduce-input.json", initial)
        report, code = self.cli("reduce", "--input", source, "--command-file", command,
                                "--cwd", self.output, "--max-calls", "32",
                                "--max-seconds", "10", "--timeout", "2")
        reduced = report.get("reduced_items")
        checks = {"cli_success": code == 0,
                  "expected_two_item_reproduction": reduced == ["CONNECT", "CLOSE"],
                  "fresh_failure_preserved": report.get("failure_preserved") is True,
                  "original_fixture_retained": json.loads(source.read_text(encoding="utf-8")) == initial}
        return self.case("reproduction_reduction", report, checks)

    def priority(self) -> dict:
        script = self.text("ordered_check.py", CHECK)
        labels = ["slow-pass", "fast-pass", "fast-failure"]
        checks = [(label, [sys.executable, "-I", str(script), label]) for label in labels]
        history = {"schema": "parcimonia.test-history/v1", "runs": []}
        observed = []
        for label, command in checks:
            result = invoke_json(command, {}, cwd=self.output, timeout_seconds=2)
            observed.append({"label": label, "command": command, "result": result})
            history = append_observations(history, [{
                "label": label, "command_sha256": command_fingerprint(command),
                "duration_ms": result["elapsed_ms"], "outcome": result["status"]}])
        payload = self.data("priority-input.json", {
            "checks": [{"label": label, "command": command} for label, command in checks],
            "history": history})
        order, code = self.cli("prioritize", "--input", payload)
        commands = dict(checks)
        rerun = []
        for row in order.get("ordered", []):
            label = row["label"]
            result = invoke_json(commands[label], {}, cwd=self.output, timeout_seconds=2)
            rerun.append({"label": label, "command": commands[label], "result": result})
        checks_out = {"cli_success": code == 0,
                      "all_three_checks_retained": sorted(row["label"] for row in rerun) == sorted(labels),
                      "known_failure_scheduled_first": bool(rerun) and rerun[0]["label"] == "fast-failure",
                      "actual_expected_outcomes": all(row["result"]["status"] == (
                          "failed" if row["label"] == "fast-failure" else "passed") for row in observed + rerun),
                      "no_required_checks_omitted": order.get("omitted") == 0}
        return self.case("test_prioritization", {"ordering": order,
                         "history_origin": "actual_authored_subprocess_observations_this_run",
                         "initial_observations": observed, "ordered_observations": rerun}, checks_out)

    def mutation(self) -> dict:
        project = self.output / "mutation-project"
        project.mkdir()
        subject = self.text("mutation-project/subject.py", "def allowed(age):\n    return age >= 18\n")
        test = self.text("mutation-project/test_subject.py",
                        "import unittest\nfrom subject import allowed\n\n"
                        "class WeakBoundaryTest(unittest.TestCase):\n"
                        "    def test_adult(self):\n        self.assertTrue(allowed(40))\n")
        before = {str(path.name): _sha(path.read_bytes()) for path in (subject, test)}
        report, code = self.cli("mutate", "--project", project, "--source", "subject.py",
                                "--tests", "test_subject.py", "--max-mutants", "2",
                                "--timeout", "3", "--max-seconds", "15", timeout=25)
        counts = report.get("counts", {})
        checks = {"survivor_finding_exit": code == 1,
                  "baseline_completed": report.get("baseline", {}).get("status") == "passed",
                  "actual_survivor_detected": counts.get("survived", 0) >= 1,
                  "no_inconclusive_mutants": counts.get("inconclusive") == 0,
                  "original_files_unchanged": before == {
                      str(path.name): _sha(path.read_bytes()) for path in (subject, test)}}
        return self.case("mutation_checks", report, checks)

    def exploration(self) -> dict:
        scope = "authored-verification-demo"

        def page(state, links=(), terminal=False):
            return (f'<meta name="parcimonia-state" content="{state}">'
                    f'<meta name="parcimonia-scope" content="{scope}">'
                    f'<meta name="parcimonia-terminal" content="{str(terminal).lower()}">'
                    + "".join(f'<a data-action="{action}" href="{path}">{action}</a>'
                              for action, path in links)).encode("utf-8")

        pages = {"/": page("home", (("settings", "/settings"), ("help", "/help"))),
                 "/settings": page("settings", (("finish", "/done"), ("home", "/"))),
                 "/help": page("help"), "/done": page("done", terminal=True)}
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                body = pages.get(self.path)
                self.send_response(200 if body is not None and len(requests) <= 64 else 404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body or b"")))
                self.end_headers()
                self.wfile.write(body or b"")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05),
                                  daemon=True)
        thread.start()
        try:
            actions = self.data("http-actions.json", ["settings", "help", "finish", "home"])
            paths = self.data("http-paths.json", list(pages))
            goals = self.data("http-goals.json", ["done"])
            self.data("http-pages.json", {path: raw.decode("utf-8") for path, raw in pages.items()})
            report, code = self.cli("explore", "--origin", f"http://127.0.0.1:{server.server_port}/",
                                    "--scope", scope, "--actions", actions, "--paths", paths,
                                    "--goals", goals, "--max-actions", "24", "--max-states", "8",
                                    "--max-seconds", "5", timeout=10)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        expected_edges = {("home", "settings", "settings"), ("home", "help", "help"),
                          ("settings", "finish", "done"), ("settings", "home", "home")}
        edges = {(row.get("source"), row.get("action"), row.get("target"))
                 for row in report.get("transitions", []) if row.get("status") == "observed"}
        checks = {"cli_success": code == 0,
                  "actual_http_adapter": report.get("adapter_kind") == "http_navigation",
                  "independent_expected_edges": edges == expected_edges,
                  "independent_expected_states": {row["state_id"] for row in report.get("states", [])}
                      == {"home", "settings", "help", "done"},
                  "independent_dead_end": report.get("dead_ends") == ["help"],
                  "independent_goal": report.get("coverage", {}).get("goals_observed") == ["done"],
                  "requests_stayed_in_authored_scope": bool(requests) and set(requests) <= set(pages),
                  "no_graphical_qualification_claim": report.get("boundaries", {}).get("graphical_qualification") is False}
        return self.case("interface_exploration", {"exploration": report,
                         "observed_http_requests": requests,
                         "scope": "authored_loopback_html_not_graphical_ui"}, checks)

    def triage(self) -> dict:
        oracle = self.text("triage_oracle.py", ORACLE)
        command = self.data("triage-command.json", [sys.executable, "-I", str(oracle), "triage"])
        context = self.data("triage-context.json", {"scenario": "alternating_authored_fixture", "version": 1})
        report, code = self.cli("triage", "--command-file", command, "--cwd", self.output,
                                "--context", context, "--seed", "7", "--attempts", "4",
                                "--max-seconds", "10", "--timeout", "2")
        attempts = report.get("attempts", [])
        checks = {"failure_observation_exit": code == 1,
                  "intermittency_observed": report.get("classification") == "intermittent_observed",
                  "all_attempts_retained": len(attempts) == 4,
                  "expected_order_retained": [a["reported_status"] for a in attempts]
                      == ["failed", "passed", "failed", "passed"],
                  "fixed_seed": all(a["seed"] == 7 for a in attempts),
                  "fixed_context_observed": all(a["context_match"] is True for a in attempts),
                  "first_failure_not_erased": report.get("failure_ever_reported") is True
                      and report.get("reported_counts", {}).get("failed") == 2}
        return self.case("intermittent_failure_triage", report, checks)

    def conformance(self, cloud_root: Path | None) -> dict:
        if cloud_root is None:
            return {"id": "cloud_local_conformance", "status": "not_run", "verified": False,
                    "reason": "explicit_trusted_cloud_source_not_supplied", "assertions": {}}
        report, code = self.cli("conformance", "--cloud-root", cloud_root, timeout=30)
        if report.get("status") == "not_run":
            return {"id": "cloud_local_conformance", "status": "not_run", "verified": False,
                    "report": report, "assertions": {}}
        checks = {"cli_success": code == 0,
                  "comparison_report_passed": report.get("passed") is True,
                  "actual_cases_compared": report.get("case_count", 0) > 0
                      and len(report.get("results", [])) == report.get("case_count"),
                  "source_unchanged": report.get("source_unchanged_after_comparison") is True,
                  "local_helpers_not_deployed_service": report.get("scope")
                      == "local_source_helpers_not_deployed_service_or_mcp_wrappers"}
        return self.case("cloud_local_conformance", report, checks)

    @staticmethod
    def case(identifier: str, report: dict, checks: dict) -> dict:
        passed = bool(checks) and all(value is True for value in checks.values())
        return {"id": identifier, "status": "passed" if passed else "failed",
                "verified": passed, "assertions": checks, "report": report}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path,
                        help="new absolute directory outside this repository; never overwritten")
    parser.add_argument("--cloud-root", type=Path,
                        help="explicit trusted local cloud-source checkout, not a deployed URL")
    args = parser.parse_args(argv)
    output = args.out.resolve()
    if not args.out.is_absolute() or output.is_relative_to(ROOT.resolve()):
        parser.error("--out must be an absolute path outside this repository")
    if output.exists():
        parser.error("--out already exists; choose a fresh directory")
    output.mkdir(parents=True, exist_ok=False)
    initial_sources = _sources()
    demo = Demonstration(output)
    cases = []
    for identifier, function in (("reproduction_reduction", demo.reduction),
                                 ("test_prioritization", demo.priority),
                                 ("cloud_local_conformance", lambda: demo.conformance(args.cloud_root)),
                                 ("mutation_checks", demo.mutation),
                                 ("interface_exploration", demo.exploration),
                                 ("intermittent_failure_triage", demo.triage)):
        try:
            cases.append(function())
        except Exception as error:
            cases.append({"id": identifier, "status": "failed", "verified": False,
                          "reason": "demonstration_exception", "error_type": type(error).__name__,
                          "assertions": {}})
    unchanged = initial_sources == _sources()
    counts = {status: sum(case["status"] == status for case in cases)
              for status in ("passed", "failed", "not_run")}
    status = "failed" if counts["failed"] else "partial" if counts["not_run"] or not unchanged else "passed"
    report = {"schema": "parcimonia.verification-demo/v1", "status": status,
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "origin": "authored_fixtures_not_real_user_bug_or_savings_benchmark",
              "runtime_version": __version__, "python_version": platform.python_version(),
              "source_revision": _revision(), "source_files": initial_sources,
              "source_unchanged_after_demonstration": unchanged,
              "fixture_files": demo.fixtures, "commands": demo.commands,
              "cases": cases, "case_counts": counts,
              "verified_case_count": counts["passed"] if unchanged else 0,
              "verified_assertions": sum(sum(value is True for value in case["assertions"].values())
                                         for case in cases if case["verified"]) if unchanged else 0,
              "host_measurements": {"provider_tokens": None, "cost": None,
                                    "end_to_end_acceleration": None, "savings": None},
              "limits": ["Authored fixtures establish these executed contracts only.",
                         "HTTP traversal is not graphical UI or real-time game qualification.",
                         "Local cloud-source comparison does not test the deployed service.",
                         "Child/helper timings exclude host reasoning and do not establish savings."]}
    _json_file(output / "parcimonia-verification.json", report)
    print(json.dumps({"status": status, "case_counts": counts,
                      "verified_assertions": report["verified_assertions"],
                      "report": str(output / "parcimonia-verification.json")}, ensure_ascii=True))
    return 0 if status == "passed" else 1 if status == "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
