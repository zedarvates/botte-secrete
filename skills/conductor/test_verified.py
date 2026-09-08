"""Behavioral tests for evidence-gated execution and conservative resumption."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.conductor.verified import PLAN_SCHEMA, execute_verified, read_document


def step(identifier, *, needs=(), capability="worker", command="python worker.py", ensures=None):
    return {"id": identifier, "capability": capability, "command": command, "local": True,
            "needs": list(needs), "requires": [], "ensures": ensures if ensures is not None else
            [{"kind": "text_contains", "path": identifier + ".txt", "value": "done"}],
            "observes": [], "source_hashes": {}}


def plan(*steps):
    return {"schema": PLAN_SCHEMA, "goal": "Vérifier les résultats du projet de test",
            "context": "isolated-fixture-v1", "steps": list(steps)}


class VerifiedRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.calls = []

    def run_plan(self, p, **kwargs):
        return execute_verified(p, cwd=str(self.root), **kwargs)

    def write(self, path, value="done"):
        (self.root / path).write_text(value, encoding="utf-8")

    def test_zero_exit_without_required_artifact_blocks_only_descendants(self):
        p = plan(step("build"), step("consume", needs=["build"]), step("independent"))
        def runner(command, cwd, timeout):
            self.calls.append(command)
            if len(self.calls) == 2:
                self.write("independent.txt")
            return 0, "claimed success"
        report = self.run_plan(p, confirm=True, runner=runner)
        self.assertEqual([r["status"] for r in report["results"]],
                         ["unverified", "blocked", "verified"])
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(report["complete"])

    def test_resume_rechecks_success_and_runs_only_previously_blocked_step(self):
        first = step("first", capability="metrics", command="python -m skills.metrics.cli .")
        p = plan(first, step("second", needs=["first"]))
        def runner(command, cwd, timeout):
            self.calls.append(command)
            self.write("first.txt" if len(self.calls) == 1 else "second.txt")
            return 0, "ok"
        before = self.run_plan(p, checkpoint="run.json", runner=runner)
        self.assertEqual(before["summary"]["blocked"], 1)
        after = self.run_plan(p, checkpoint="run.json", resume=True, confirm=True, runner=runner)
        self.assertTrue(after["complete"])
        self.assertTrue(after["results"][0]["reused"])
        self.assertEqual(after["run_id"], before["run_id"])
        self.assertEqual(len(self.calls), 2)

    def test_changed_output_prevents_reuse_and_descendant_dispatch(self):
        p = plan(step("first"), step("second", needs=["first"]))
        def runner(command, cwd, timeout):
            self.write("first.txt")
            self.write("second.txt")
            return 0, "ok"
        self.run_plan(p, confirm=True, checkpoint="run.json", runner=runner)
        self.write("first.txt", "corrupted")
        with patch("skills.conductor.verified._default_runner") as call:
            result = self.run_plan(p, resume=True, checkpoint="run.json", confirm=True)
        call.assert_not_called()
        self.assertEqual(result["results"][0]["status"], "stale")
        self.assertEqual(result["results"][1]["status"], "stale")
        self.assertFalse(result["complete"])

    def test_timeout_with_partial_write_is_recorded_and_never_automatically_retried(self):
        p = plan(step("partial"), step("later", needs=["partial"]))
        def runner(command, cwd, timeout):
            self.write("partial.txt", "in progress")
            return -1, "timeout after write"
        result = self.run_plan(p, confirm=True, checkpoint="run.json", runner=runner)
        self.assertEqual(result["results"][0]["status"], "uncertain")
        self.assertEqual(result["results"][0]["changed_paths"], ["partial.txt"])
        with patch("skills.conductor.verified._default_runner") as call:
            resumed = self.run_plan(p, confirm=True, checkpoint="run.json", resume=True)
        call.assert_not_called()
        self.assertFalse(resumed["complete"])

    def test_changed_required_input_invalidates_reuse_and_preserves_historical_checks(self):
        self.write("input.csv", "c,600\n")
        producer = step("producer")
        producer["requires"] = [{"kind": "file_sha256", "path": "input.csv",
                                 "value": hashlib.sha256(b"c,600\n").hexdigest()}]
        p = plan(producer, step("consumer", needs=["producer"]))
        def runner(command, cwd, timeout):
            self.write("producer.txt")
            self.write("consumer.txt")
            return 0, "ok"
        self.assertTrue(self.run_plan(p, confirm=True, checkpoint="run.json", runner=runner)["complete"])
        self.assertTrue(self.run_plan(p, confirm=True, checkpoint="run.json", resume=True)["complete"])
        self.write("input.csv", "c,700\n")
        with patch("skills.conductor.verified._default_runner") as run:
            r = self.run_plan(p, confirm=True, checkpoint="run.json", resume=True)
        run.assert_not_called()
        self.assertFalse(r["complete"])
        self.assertEqual([row["status"] for row in r["results"]], ["stale", "stale"])
        self.assertFalse(any(row["reused"] for row in r["results"]))
        self.assertTrue(r["results"][0]["precondition_checks"][0]["passed"])
        self.assertFalse(r["results"][0]["resume_precondition_checks"][0]["passed"])

    def test_changed_required_input_blocks_dependency_consumption(self):
        self.write("input.csv", "c,600\n")
        producer = step("producer")
        producer["requires"] = [{"kind": "file_sha256", "path": "input.csv",
                                 "value": hashlib.sha256(b"c,600\n").hexdigest()}]
        p = plan(producer, step("change"), step("consumer", needs=["producer"]))
        def runner(command, cwd, timeout):
            self.calls.append(command)
            self.write("producer.txt")
            self.write("change.txt")
            if len(self.calls) == 2:
                self.write("input.csv", "c,700\n")
            return 0, "ok"
        r = self.run_plan(p, confirm=True, runner=runner)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(r["results"][2]["status"], "blocked")
        latest = r["results"][2]["dependency_checks"]["producer"]
        self.assertFalse(latest["precondition_checks"][0]["passed"])
        self.assertTrue(latest["postcondition_checks"][0]["passed"])

    def test_interrupt_persists_dispatch_before_runner_and_uncertainty_after(self):
        p = plan(step("work"))
        def runner(command, cwd, timeout):
            checkpoint = read_document(self.root / "run.json")
            self.assertEqual(checkpoint["results"][0]["status"], "running")
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_plan(p, confirm=True, checkpoint="run.json", runner=runner)
        self.assertEqual(read_document(self.root / "run.json")["results"][0]["status"], "uncertain")
        self.assertFalse((self.root / "run.json.lock").exists())

    def test_failed_process_cannot_pass_even_when_postconditions_exist(self):
        self.write("work.txt")
        r = self.run_plan(plan(step("work")), confirm=True, runner=lambda *a: (2, "error"))
        self.assertEqual(r["results"][0]["status"], "failed")

    def test_no_postconditions_remains_explicitly_unverified(self):
        r = self.run_plan(plan(step("work", ensures=[])), confirm=True, runner=lambda *a: (0, "ok"))
        self.assertEqual(r["results"][0]["status"], "unverified")

    def test_precondition_and_source_changes_prevent_execution(self):
        self.write("worker.py", "initial")
        s = step("work")
        s["source_hashes"] = {"worker.py": hashlib.sha256(b"initial").hexdigest()}
        s["requires"] = [{"kind": "file_exists", "path": "input.txt"}]
        for missing_input in (True, False):
            if not missing_input:
                self.write("input.txt")
                self.write("worker.py", "new code")
            with patch("skills.conductor.verified._default_runner") as call:
                r = self.run_plan(plan(s), confirm=True)
            call.assert_not_called()
            self.assertEqual(r["results"][0]["status"], "blocked")

    def test_dependency_is_rechecked_just_before_consumption(self):
        p = plan(step("build"), step("change"), step("consumer", needs=["build"]))
        def runner(command, cwd, timeout):
            self.calls.append(command)
            self.write("build.txt", "done" if len(self.calls) == 1 else "invalidated")
            self.write("change.txt")
            return 0, "ok"
        r = self.run_plan(p, confirm=True, runner=runner)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(r["results"][2]["status"], "blocked")

    def test_capability_label_and_effects_cannot_unlock_an_arbitrary_command(self):
        s = step("work", capability="metrics", command="python destructive.py")
        s["effects_before"] = {"safe": True, "evidence": "execute something"}
        with patch("skills.conductor.verified._default_runner") as call:
            r = self.run_plan(plan(s))
        call.assert_not_called()
        self.assertEqual(r["results"][0]["status"], "blocked")
        self.assertEqual(r["results"][0]["effects_before"], s["effects_before"])

    def test_invalid_dependency_or_late_invalid_step_prevents_all_execution(self):
        for invalid in (step("late", needs=["missing"]), step("ok")):
            p = plan(step("ok"), invalid)
            with patch("skills.conductor.verified._default_runner") as call:
                r = self.run_plan(p, confirm=True, checkpoint="run.json")
            call.assert_not_called()
            self.assertIn("error", r)
            self.assertFalse((self.root / "run.json").exists())

    def test_scope_checks_reject_traversal_and_dangling_symlinks(self):
        for path in ("../other", "/tmp/other", "C:/other", "x\\y", "x:stream"):
            with self.subTest(path=path):
                r = self.run_plan(plan(step("work", ensures=[{"kind": "file_absent", "path": path}])))
                self.assertIn("error", r)
        try:
            (self.root / "link").symlink_to(self.root / "missing")
        except OSError:
            self.skipTest("symlinks unavailable")
        s = step("work", ensures=[{"kind": "file_absent", "path": "link"}])
        r = self.run_plan(plan(s), confirm=True, runner=lambda *a: (0, "ok"))
        self.assertEqual(r["results"][0]["status"], "unverified")

    def test_dry_run_creates_no_checkpoint_and_reads_no_observations(self):
        with patch("skills.conductor.verified._read") as read, \
             patch("skills.conductor.verified._default_runner") as run:
            r = self.run_plan(plan(step("work")), dry_run=True, checkpoint="private/run.json")
        read.assert_not_called()
        run.assert_not_called()
        self.assertEqual(r["mode"], "dry_run")
        self.assertFalse((self.root / "private").exists())

    def test_checkpoint_lock_and_mismatched_plan_cannot_dispatch(self):
        self.write("run.json.lock", "other writer")
        with patch("skills.conductor.verified._default_runner") as run:
            r = self.run_plan(plan(step("work")), confirm=True, checkpoint="run.json")
        self.assertIn("error", r)
        run.assert_not_called()
        (self.root / "run.json.lock").unlink()
        p = plan(step("work"))
        self.run_plan(p, checkpoint="run.json")
        p["context"] = "different environment"
        with patch("skills.conductor.verified._default_runner") as run:
            r = self.run_plan(p, checkpoint="run.json", resume=True, confirm=True)
        self.assertIn("error", r)
        run.assert_not_called()

    def test_json_checks_use_typed_values_and_escaped_pointer(self):
        self.write("data.json", '{"a/b":{"~key":[true]}}')
        c = {"kind": "json_equals", "path": "data.json", "pointer": "/a~1b/~0key/0", "value": True}
        self.assertTrue(self.run_plan(plan(step("work", ensures=[c])), confirm=True,
                                      runner=lambda *a: (0, "ok"))["complete"])
        c["value"] = 1
        self.assertFalse(self.run_plan(plan(step("work", ensures=[c])), confirm=True,
                                       runner=lambda *a: (0, "ok"))["complete"])

    def test_real_subprocess_artifact_and_compact_evidence(self):
        self.write("worker.py", "from pathlib import Path\nPath('work.txt').write_text('done', encoding='utf-8')\nprint('private output fixture')\n")
        r = self.run_plan(plan(step("work")), confirm=True, checkpoint="run.json")
        self.assertTrue(r["complete"])
        self.assertNotIn("private output fixture", json.dumps(r))
        self.assertEqual(r["results"][0]["after"]["work.txt"]["sha256"], hashlib.sha256(b"done").hexdigest())

    def test_cli_incomplete_execution_is_nonzero_and_preview_is_zero(self):
        from skills.conductor.cli import main
        self.write("plan.json", json.dumps(plan(step("work"))))
        args = ["--plan", str(self.root / "plan.json"), "--project", str(self.root)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
            self.assertEqual(main(args + ["--execute"]), 1)

    def test_mcp_defaults_to_preview_and_rejects_truthy_string_confirmation(self):
        from skills.llm_mcp.server import handle
        def request(args):
            raw = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "execute_verified_plan", "arguments": args}})
            return json.loads(raw["result"]["content"][0]["text"])
        args = {"plan": plan(step("work")), "project": str(self.root)}
        with patch("skills.conductor.verified._default_runner") as run:
            self.assertEqual(request(args)["mode"], "dry_run")
            args.update(dry_run=False, confirm="false")
            self.assertIn("error", request(args))
        run.assert_not_called()


def main():
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(VerifiedRunTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
