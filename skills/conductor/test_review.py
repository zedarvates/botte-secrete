"""Shared review regressions with isolated declarations and execution evidence."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request

from skills.capabilities import Capability
from skills.capabilities.effects import contract_template, inspect_effects
from skills.capabilities.network_observations import network_attempt
from skills.capabilities.observations import ObservationSession, empty_report, observed_file_write, validate_report
from skills.capabilities.review import after, before
from skills.conductor import execute, plan, run_goal
from skills.conductor.cli import main as cli


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.skill = self.root / "skills" / "metrics"
        self.contract = self.make_skill(self.skill)
        self.caps = [Capability("metrics", "SENSE", "fixture", "skills/metrics/SKILL.md", True)]
        self.picked = [{"name": "metrics", "path": self.caps[0].path, "score": 1, "why": "fixture"}]
        for target, value in (("skills.capabilities.registry.REPO_ROOT", self.root),
                              ("skills.conductor.conductor.REPO_ROOT", self.root)):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, value in (("skills.conductor.conductor.load_caps", self.caps),
                              ("skills.conductor.conductor.curate", self.picked)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_skill(self, directory):
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("---\nname: metrics\ndescription: fixture\n---\n", encoding="utf-8")
        identity = "zedarvates/botte-secrete:" + directory.relative_to(self.root).as_posix()
        contract = contract_template(directory, identity)
        (directory / "effects.json").write_text(json.dumps(contract), encoding="utf-8")
        return contract

    def test_selected_only_inspection_and_no_implicit_full_payload_or_network(self):
        ordinary = plan("fixture")
        with patch("skills.capabilities.effects.inspect_effects", wraps=inspect_effects) as inspect, \
             patch("socket.socket.connect", side_effect=AssertionError("unexpected network")):
            compact = plan("fixture", review_effects=True)
        inspect.assert_called_once_with(self.skill)
        step = compact["steps"][0]
        self.assertEqual(step.pop("review_before")["source"], self.caps[0].path)
        self.assertNotIn("effects", step)
        compact.pop("review_method")
        self.assertEqual(compact, ordinary)
        with patch("skills.capabilities.effects.inspect_effects", wraps=inspect_effects) as inspect:
            detailed = plan("fixture", review_effects=True, include_effects=True)
        inspect.assert_called_once_with(self.skill)
        self.assertEqual(detailed["steps"][0]["effects"]["contract"], self.contract)

    def test_homonyms_keep_source_identity_and_execution_classification(self):
        other = self.root / "skills" / "vendor" / "metrics"
        contract = self.make_skill(other)
        self.caps.append(Capability("metrics", "GOVERN", "fixture", "skills/vendor/metrics/SKILL.md", True))
        self.picked.append({"name": "metrics", "path": self.caps[1].path, "score": 1, "why": "fixture"})
        selected = plan("fixture", review_effects=True)
        self.assertEqual([s["review_before"]["capability_id"] for s in selected["steps"]],
                         [self.contract["capability_id"], contract["capability_id"]])
        calls = []
        result = execute(selected, confirm=True, runner=lambda *args: (calls.append(args) or (0, "done")))
        self.assertEqual(len(calls), 1)
        self.assertEqual([r["status"] for r in result["results"]], ["ran", "skipped"])

    def test_missing_invalid_stale_and_uninspected_are_not_collapsed(self):
        sidecar = self.skill / "effects.json"
        sidecar.unlink()
        self.assertEqual(before(inspect_effects(self.skill))["declaration"], "missing")
        sidecar.write_text("{", encoding="utf-8")
        self.assertEqual(before(inspect_effects(self.skill))["declaration"], "invalid")
        sidecar.write_text(json.dumps(self.contract), encoding="utf-8")
        (self.skill / "SKILL.md").write_text("changed", encoding="utf-8")
        stale = before(inspect_effects(self.skill))
        self.assertEqual(stale["declaration"], "stale")
        self.assertIn("declaration_stale", stale["attention"])
        self.assertEqual(before(None)["declaration"], "not_inspected")
        self.assertEqual(before({"status": "declared", "contract": {}})["declaration"], "invalid")

    def test_compact_projection_defers_prose_without_inventing_operation_safety(self):
        self.contract["analysis"]["summary"] = "fixture-prose-that-must-stay-in-sidecar " * 200
        brief = before({"status": "declared", "contract": self.contract})
        self.assertNotIn("fixture-prose", json.dumps(brief))
        self.assertEqual(brief["detail_counts"]["reuse"], len(self.contract["reuse"]))
        self.assertEqual(brief["operation_assessment"], "deferred")
        self.assertIn("unknown_effects", brief["attention"])

    def test_before_snapshot_survives_runner_mutation_and_failure(self):
        selected = plan("fixture", review_effects=True)
        original = deepcopy(selected["steps"][0]["review_before"])
        def runner(*_):
            selected["steps"][0]["review_before"]["attention"].clear()
            return 1, "partial work"
        result = execute(selected, runner=runner)["results"][0]
        self.assertEqual(result["review_before"], original)
        self.assertEqual(result["review_after"]["next_action"], "inspect_state_before_retry")
        self.assertEqual(result["review_after"]["task_outcome"], "unverified")

    def test_review_alone_does_not_start_observation_or_unlock_gates(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), \
                 patch("skills.conductor.observed_run.run_observed") as observer, \
                 patch("skills.conductor.executor._default_runner") as runner:
                result = execute({"steps": [{"capability": "unknown", "command": "write data"}]},
                                 review_effects=True, dry_run=dry_run)["results"][0]
            observer.assert_not_called()
            runner.assert_not_called()
            self.assertEqual(result["review_after"]["coverage"], "not_run")
            self.assertEqual(result["review_before"]["declaration"], "not_inspected")

    def test_successful_process_preserves_swallowed_child_write_failure(self):
        path = self.root / "output.json"
        def runner(*_):
            with session.call(self.skill, "parent"):
                try:
                    with session.call(self.skill, "child"), observed_file_write(path, "/expected_effects/0"):
                        path.write_text("partial", encoding="utf-8")
                        raise OSError("fixture failure after writing")
                except OSError:
                    pass
            return 0, "returned"
        # execute's observed runner owns the real session; use its enrolled context.
        from skills.capabilities.observations import _SESSION
        def observed_runner(*args):
            nonlocal session
            session = _SESSION.get()
            return runner(*args)
        session = None
        result = run_goal("fixture", review_effects=True, observe_effects=True,
                          runner=observed_runner)["results"][0]
        review = result["review_after"]
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(review["observed_counts"]["failed_writes"], 1)
        self.assertIn("nested_failure", review["attention"])
        self.assertEqual(review["next_action"], "inspect_state_before_retry")
        self.assertEqual(review["task_outcome"], "unverified")
        self.assertEqual(path.read_text(encoding="utf-8"), "partial")

    def test_http_response_is_only_partial_evidence(self):
        url = "http://127.0.0.1/fixture"
        with ObservationSession() as session, session.call(self.skill, "model_call"):
            with network_attempt("http", Request(url), "/expected_effects/0", method="POST") as attempt:
                attempt.response(SimpleNamespace(getcode=lambda: 200, geturl=lambda: url))
                attempt.read_complete()
        session.report["process"] = {"status": "exited", "exit_code": 0}
        self.assertEqual(validate_report(session.report), [])
        review = after({"status": "ran", "effects_observed": session.report}, before(inspect_effects(self.skill)))
        self.assertEqual(review["observed_counts"]["http_responses"], 1)
        self.assertEqual(review["task_outcome"], "unverified")
        self.assertEqual(review["coverage"], "partial")

    def test_changed_declaration_in_later_call_is_visible(self):
        prior = before(inspect_effects(self.skill))
        with ObservationSession() as session:
            with session.call(self.skill, "first"):
                pass
            self.contract["contract_version"] = "0.9.0"
            (self.skill / "effects.json").write_text(json.dumps(self.contract), encoding="utf-8")
            with session.call(self.skill, "second"):
                pass
        session.report["process"] = {"status": "exited", "exit_code": 0}
        review = after({"status": "ran", "effects_observed": session.report}, prior)
        self.assertTrue(review["declaration_changed"])
        self.assertIn("declaration_changed", review["attention"])

    def test_interruption_limits_and_malformed_evidence_remain_visible(self):
        observed = empty_report()
        observed["process"] = {"status": "timed_out", "exit_code": -1}
        observed["problems"] = ["checkpoint size limit reached"]
        review = after({"status": "failed", "effects_observed": observed}, before(None))
        self.assertEqual(review["next_action"], "inspect_state_before_retry")
        self.assertIn("observation_problems", review["attention"])
        review = after({"status": "ran", "effects_observed": {}}, before(None))
        self.assertEqual(review["coverage"], "invalid_evidence")
        self.assertEqual(review["task_outcome"], "unverified")

    def test_blocked_or_skipped_with_execution_evidence_is_not_reported_as_not_run(self):
        with ObservationSession() as session, session.call(self.skill, "already attempted"):
            pass
        for status in ("blocked", "skipped"):
            for process in ({"status": "exited", "exit_code": 0},
                            {"status": "not_run", "exit_code": None}):
                with self.subTest(status=status, process=process):
                    session.report["process"] = process
                    review = after({"status": status, "exit_code": None,
                                    "effects_observed": session.report}, {})
                    self.assertEqual(review["task_outcome"], "unverified")
                    self.assertEqual(review["coverage"], "partial")
                    self.assertIn("process_evidence_mismatch", review["attention"])
                    self.assertEqual(review["evidence_ref"], "effects_observed")
                    self.assertEqual(review["next_action"], "inspect_state_before_retry")

    def test_review_compares_process_completion_and_codes_without_inventing_success(self):
        cases = [("ran", 0, "exited", 0, False),
                 ("ran", 0, "running", None, True),
                 ("ran", 0, "not_run", None, True),
                 ("failed", 1, "exited", 1, False),
                 ("failed", -1, "timed_out", -1, False),
                 ("failed", -1, "launch_failed", -1, False),
                 ("failed", -1, "runner_error", -1, False),
                 ("failed", 1, "exited", 0, True),
                 ("failed", 1, "exited", 2, True),
                 ("failed", 1, "running", 1, True),
                 ("failed", 1, "not_run", 1, True),
                 ("blocked", None, "not_run", None, False),
                 ("skipped", None, "not_run", 1, True)]
        for status, code, process_status, process_code, mismatch in cases:
            with self.subTest(status=status, process=process_status, code=process_code):
                observed = empty_report()
                observed["process"] = {"status": process_status, "exit_code": process_code}
                review = after({"status": status, "exit_code": code, "effects_observed": observed}, {})
                self.assertEqual("process_evidence_mismatch" in review["attention"], mismatch)
                if mismatch or status in {"ran", "failed"}:
                    self.assertEqual(review["task_outcome"], "unverified")
                if mismatch:
                    self.assertEqual(review["next_action"], "inspect_state_before_retry")

    def test_invalid_in_memory_evidence_never_claims_non_execution_or_breaks_review(self):
        cyclic = {}
        cyclic["cycle"] = cyclic
        for observed in ({}, cyclic, {"value": object()}, {"value": float("nan")},
                         {"value": "\ud800"}):
            for status in ("ran", "failed", "blocked", "skipped"):
                with self.subTest(status=status, type=type(observed)):
                    review = after({"status": status, "effects_observed": observed}, {})
                    self.assertEqual(review["coverage"], "invalid_evidence")
                    self.assertEqual(review["task_outcome"], "unverified")
                    self.assertEqual(review["next_action"], "inspect_state_before_retry")
                    self.assertNotIn("evidence_ref", review)

    def test_oversized_companion_is_rejected_before_graph_validation_without_mutation(self):
        observed = empty_report()
        original = deepcopy(observed)
        with patch("skills.capabilities.review.MAX_REPORT_BYTES", 10), \
             patch("skills.capabilities.review.validate_report") as validate:
            review = after({"status": "blocked", "effects_observed": observed}, {})
        validate.assert_not_called()
        self.assertEqual(observed, original)
        self.assertEqual(review["task_outcome"], "unverified")
        self.assertIn("observation_report_too_large", review["attention"])
        self.assertNotIn("evidence_ref", review)

    def test_executor_keeps_conflicting_evidence_and_does_not_repeat_the_operation(self):
        observed = empty_report()
        observed["process"] = {"status": "exited", "exit_code": 0}
        with patch("skills.conductor.observed_run.run_observed",
                   return_value=(1, "partial", observed)) as runner:
            result = execute(plan("fixture", review_effects=True), observe_effects=True)
        runner.assert_called_once()
        step = result["results"][0]
        self.assertEqual(step["status"], "failed")
        self.assertEqual(step["exit_code"], 1)
        self.assertEqual(step["effects_observed"], observed)
        self.assertIn("process_evidence_mismatch", step["review_after"]["attention"])
        self.assertEqual(step["review_after"]["task_outcome"], "unverified")

    def test_stop_after_partial_failure_retains_all_positions_and_observations(self):
        from skills.capabilities.observations import _SESSION
        source = plan("fixture", review_effects=True)["steps"][0]
        steps = [{**source, "order": 7, "command": name} for name in ("first", "second", "third")]
        calls = []
        def runner(command, *_):
            calls.append(command)
            path = self.root / (command + ".txt")
            with _SESSION.get().call(self.skill, command), observed_file_write(path, "/expected_effects/0"):
                path.write_text("completed" if command == "first" else "partial", encoding="utf-8")
                if command == "second":
                    raise OSError("fixture failure after mutation")
            return 0, "done"
        result = execute({"steps": steps}, runner=runner, observe_effects=True, stop_on_failure=True)
        self.assertEqual(calls, ["first", "second"])
        self.assertEqual(result["stopped_after_result_index"], 1)
        self.assertEqual(result["summary"], {"ran": 1, "failed": 1, "blocked": 0, "skipped": 1})
        self.assertEqual([r["order"] for r in result["results"]], [7, 7, 7])
        self.assertEqual((self.root / "first.txt").read_text(encoding="utf-8"), "completed")
        self.assertEqual((self.root / "second.txt").read_text(encoding="utf-8"), "partial")
        self.assertFalse((self.root / "third.txt").exists())
        failed, pending = result["results"][1:]
        self.assertEqual(failed["effects_summary"]["failed_writes"], 1)
        self.assertEqual(failed["review_after"]["next_action"], "inspect_state_before_retry")
        self.assertEqual(pending["effects_observed"]["process"], {"status": "not_run", "exit_code": None})
        self.assertEqual(pending["effects_observed"]["calls"], [])
        self.assertEqual(pending["review_after"]["task_outcome"], "not_run")
        self.assertIn("index 1", pending["note"])
        for row in result["results"]:
            self.assertEqual(validate_report(row["effects_observed"]), [])
            self.assertEqual(row["review_before"], source["review_before"])

    def test_stopping_is_explicit_and_does_not_read_policy_from_plan_data(self):
        steps = [{"capability": "metrics", "command": name} for name in ("first", "second")]
        for options in ({}, {"stop_on_failure": False}, {"stop_on_failure": True}):
            calls = []
            result = execute({"steps": steps, "stop_on_failure": True},
                             runner=lambda cmd, *_: (calls.append(cmd) or (1, "failed")), **options)
            enabled = options.get("stop_on_failure", False)
            self.assertEqual(calls, ["first"] if enabled else ["first", "second"])
            self.assertEqual("stop_on_failure" in result, enabled)
            self.assertEqual("stopped_after_result_index" in result, enabled)
            if enabled:
                self.assertEqual(result["stopped_after_result_index"], 0)

    def test_stop_policy_preserves_dry_run_gates_and_placeholder_classification(self):
        steps = [{"capability": "unknown", "command": "fixture write"},
                 {"capability": "metrics", "command": "fixture <argument>"}]
        for dry_run in (False, True):
            with patch("skills.conductor.executor._default_runner") as runner, \
                 patch("skills.conductor.observed_run.run_observed") as observer:
                result = execute({"steps": steps}, stop_on_failure=True,
                                 observe_effects=True, dry_run=dry_run)
            runner.assert_not_called()
            observer.assert_not_called()
            self.assertEqual([r["status"] for r in result["results"]],
                             ["skipped", "skipped"] if dry_run else ["blocked", "skipped"])
            self.assertIsNone(result["stopped_after_result_index"])
        with patch("skills.conductor.executor._default_runner", return_value=(1, "failed")) as runner:
            result = execute({"steps": [steps[0], steps[0]]}, confirm=True, stop_on_failure=True)
        runner.assert_called_once()
        self.assertEqual([r["classification"] for r in result["results"]], ["gated", "gated"])
        self.assertEqual([r["status"] for r in result["results"]], ["failed", "skipped"])

    def test_non_boolean_stop_policy_fails_before_planning_or_execution(self):
        with patch("skills.conductor.conductor.plan") as planner, \
             patch("skills.conductor.executor.classify") as classifier:
            for value in (None, 0, 1, "false", "true", []):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        run_goal("fixture", stop_on_failure=value)
                    with self.assertRaises(ValueError):
                        execute({"steps": [{}]}, stop_on_failure=value)
        planner.assert_not_called()
        classifier.assert_not_called()

    def test_successful_exit_does_not_verify_a_required_json_output(self):
        path = self.root / "required.json"
        calls = []
        def runner(command, *_):
            calls.append(command)
            if command == "producer":
                path.write_text("incomplete JSON {", encoding="utf-8")
            return 0, "returned"
        steps = [{"capability": "metrics", "command": name} for name in ("producer", "consumer")]
        result = execute({"steps": steps}, runner=runner, stop_on_failure=True, review_effects=True)
        self.assertEqual(calls, ["producer", "consumer"])
        self.assertIsNone(result["stopped_after_result_index"])
        self.assertEqual(result["results"][0]["review_after"]["task_outcome"], "unverified")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(path.read_text(encoding="utf-8"))

    def test_stop_cli_saves_complete_report_without_enabling_reviews_or_observation(self):
        from skills.capabilities.evidence import read_saved_evidence
        steps = [{"capability": "metrics", "command": name} for name in ("first", "second")]
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch("skills.conductor.conductor.plan", return_value={"goal": "fixture", "steps": steps}), \
                 patch("skills.conductor.executor._default_runner", return_value=(1, "failed")) as runner, \
                 patch("skills.conductor.observed_run.run_observed") as observer, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli(["fixture", "--execute", "--stop-on-failure", "--json", "--save", "md"])
            self.assertEqual(code, 1)
            runner.assert_called_once()
            observer.assert_not_called()
            report = json.loads(output.getvalue())
            self.assertNotIn("review_method", report)
            self.assertNotIn("effects_before", report["results"][0])
            saved = json.loads(Path(report["effects_json"]).read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            view = read_saved_evidence(report["effects_json"], overview=True)
            self.assertEqual(view["selection_status"], "overview")
            self.assertTrue(view["stop_on_failure"])
            self.assertEqual(view["stopped_after_result_index"], 0)
            self.assertEqual([r["status"] for r in view["results"]], ["failed", "skipped"])
        finally:
            os.chdir(previous)

    def test_stop_cli_requires_execution_before_any_work(self):
        with patch("skills.conductor.cli.plan") as planner, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            cli(["fixture", "--stop-on-failure"])
        self.assertEqual(error.exception.code, 2)
        planner.assert_not_called()

    def test_stop_flag_reaches_real_mcp_execution_and_keeps_invalid_values_invalid(self):
        from skills.llm_mcp.server import TOOLS, handle
        definition = next(t for t in TOOLS if t["name"] == "execute_plan")
        self.assertFalse(definition["inputSchema"]["properties"]["stop_on_failure"]["default"])
        steps = [{"capability": "metrics", "command": name} for name in ("first", "second")]
        for value in (False, True, "true"):
            with patch("skills.conductor.conductor.plan", return_value={"goal": "fixture", "steps": steps}), \
                 patch("skills.conductor.executor._default_runner", return_value=(1, "failed")) as runner:
                response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": "execute_plan", "arguments": {"goal": "fixture", "stop_on_failure": value}}})
            if isinstance(value, str):
                self.assertTrue(response["result"]["isError"])
                runner.assert_not_called()
            else:
                payload = json.loads(response["result"]["content"][0]["text"])
                self.assertEqual(runner.call_count, 1 if value else 2)
                self.assertEqual(payload["summary"]["failed"], 1 if value else 2)

    def test_mcp_opt_in_reaches_both_handlers(self):
        from skills.llm_mcp.server import TOOLS, handle
        for tool in ("conduct", "execute_plan"):
            definition = next(t for t in TOOLS if t["name"] == tool)
            self.assertFalse(definition["inputSchema"]["properties"]["review_effects"]["default"])
            for enabled in (False, True):
                with self.subTest(tool=tool, enabled=enabled):
                    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                        "name": tool, "arguments": {"goal": "fixture", "dry_run": True, "review_effects": enabled}}})
                    payload = json.loads(response["result"]["content"][0]["text"])
                    step = payload["steps" if tool == "conduct" else "results"][0]
                    self.assertEqual("review_before" in step, enabled)
                    self.assertEqual("review_after" in step, enabled and tool == "execute_plan")

    def test_cli_saves_compact_handoff_and_preserves_failure_exit(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch("skills.conductor.executor._default_runner", return_value=(1, "failed")), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli(["fixture", "--execute", "--review-effects", "--json", "--save", "md"])
            self.assertEqual(code, 1)
            payload = json.loads(output.getvalue())
            saved = json.loads(Path(payload["effects_json"]).read_text(encoding="utf-8"))
            self.assertEqual(saved, payload)
            self.assertNotIn("effects_before", saved["results"][0])
            self.assertEqual(saved["results"][0]["review_after"]["next_action"], "inspect_state_before_retry")
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
