"""Effect evidence from real fixture writes, nested calls and child timeouts."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from skills.capabilities.effects import contract_template, inspect_effects
from skills.capabilities.observations import (
    ObservationSession, file_state, summarize, validate_report,
)
from skills.capabilities import test_effects_operations as operations_fixture
from skills.conductor.executor import execute
from skills.conductor.observed_run import read_checkpoint, run_observed

REPO = Path(__file__).resolve().parents[2]


class ObservationTests(unittest.TestCase):
    # Reuse endpoint/hardware fixtures; discovery is fake, persistence is real.
    setUp = operations_fixture.OperationEffectsTests.setUp

    def test_inactive_instrumentation_does_not_inspect_or_sample(self):
        from skills.llm_backends import registry
        with patch("skills.capabilities.observations.inspect_effects") as inspect:
            with patch("skills.capabilities.observations.file_state") as sample:
                registry.save(self.backends)
        inspect.assert_not_called()
        sample.assert_not_called()
        self.assertEqual(len(registry.load()), 2)

    def test_checkup_links_real_nested_calls_and_counts_registry_write_once(self):
        from skills.checkup.cli import run
        project = self.root / "project"
        project.mkdir()
        (project / "app.py").write_text("value = 1\n", encoding="utf-8")
        with patch("skills.checkup.cli._host_prefix_summary", return_value={"available": False}):
            with patch("skills.context_profiler.profile_host", side_effect=RuntimeError("fixture")):
                with ObservationSession() as session:
                    result = run(project)
        self.assertIn("drift", result)
        report = session.report
        self.assertEqual(validate_report(report), [])
        self.assertEqual([c["operation"] for c in report["calls"]],
                         ["run", "auto_audit", "gather", "registry.refresh", "registry.save"])
        self.assertEqual([c["parent_id"] for c in report["calls"]], [None, "c1", "c2", "c3", "c4"])
        self.assertEqual(len(report["observations"]), 1)
        observation = report["observations"][0]
        self.assertEqual(observation["call_id"], "c5")
        self.assertEqual(observation["before"]["state"], "missing")
        self.assertEqual(observation["after"], file_state(self.registry_path))
        self.assertEqual(observation["comparison"], "supported")
        self.assertGreater(summarize(report)["unassessed_effects"], 0)

    def test_cached_audit_has_no_write_evidence_and_does_not_validate_effects(self):
        from skills.llm_backends import registry
        from skills.llm_backends.audit import audit
        registry.save(self.backends)
        with ObservationSession() as session:
            audit()
        self.discovery.assert_not_called()
        self.assertEqual([c["operation"] for c in session.report["calls"]], ["audit"])
        self.assertEqual(session.report["observations"], [])
        self.assertGreater(summarize(session.report)["unassessed_effects"], 0)

    def test_parent_success_keeps_swallowed_partial_write_failure(self):
        from skills.cluster import cluster
        from skills.llm_backends import registry
        registry.save(self.backends)
        lru = self.root / "lru.json"
        original_write = Path.write_text
        def partial_write(path, *args, **kwargs):
            original_write(path, *args, **kwargs)
            if path == lru:
                raise OSError("failure after mutation")
        with patch.object(cluster, "_STATE", lru), patch.object(Path, "write_text", partial_write):
            with ObservationSession() as session:
                result = cluster.status()
        self.assertEqual(result["machine_count"], 1)
        self.assertEqual(session.report["calls"][0]["status"], "returned")
        observation = session.report["observations"][0]
        self.assertEqual(observation["write_status"], "raised")
        self.assertEqual(observation["after"]["state"], "present")
        self.assertEqual(observation["comparison"], "deviation")
        self.assertEqual(summarize(session.report)["deviations"], 1)
        self.assertEqual(validate_report(session.report), [])

    def test_same_bytes_after_write_are_still_a_write_attempt(self):
        from skills.cluster import cluster
        lru = self.root / "lru.json"
        with patch.object(cluster, "_STATE", lru):
            cluster._save_state({"fixture": 1})
            with ObservationSession() as session:
                cluster._save_state({"fixture": 1})
        observation = session.report["observations"][0]
        self.assertEqual(observation["before"], observation["after"])
        self.assertEqual(observation["write_status"], "returned")
        self.assertEqual(observation["comparison"], "supported")

    def test_stale_declaration_cannot_support_a_write_facet(self):
        from skills.llm_backends import registry
        snapshot = inspect_effects(REPO / "skills" / "llm_backends")
        snapshot["status"] = "stale"
        with patch("skills.capabilities.observations.inspect_effects", return_value=snapshot):
            with ObservationSession() as session:
                registry.save(self.backends)
        self.assertEqual(session.report["observations"][0]["comparison"], "unknown")
        self.assertEqual(validate_report(session.report), [])

    def test_execution_retains_plan_and_detects_different_execution_declaration(self):
        from skills.llm_backends import registry
        snapshot = inspect_effects(REPO / "skills" / "llm_backends")
        snapshot["contract"]["contract_version"] = "0.0.0"
        step = {"order": 1, "capability": "llm_backends", "command": "fixture", "effects": snapshot}
        def runner(*_):
            registry.save(self.backends)
            return 0, "done"
        report = execute({"steps": [step]}, observe_effects=True, runner=runner)
        result = report["results"][0]
        self.assertEqual(result["effects_before"], snapshot)
        self.assertTrue(result["effects_changed_since_plan"])
        self.assertEqual(result["effects_observed"]["process"], {"status": "exited", "exit_code": 0})
        self.assertEqual(result["effects_summary"]["supported_write_facets"], 1)

    def test_dry_run_and_gates_do_not_start_observers_or_add_authority(self):
        steps = [{"order": 1, "capability": "unknown", "command": "write stuff"},
                 {"order": 2, "capability": "checkup", "command": "see skills/checkup/SKILL.md"}]
        with patch("skills.conductor.observed_run.run_observed") as runner:
            for dry_run in (False, True):
                report = execute({"steps": steps}, observe_effects=True, dry_run=dry_run)
                for result in report["results"]:
                    self.assertEqual(result["effects_observed"]["process"]["status"], "not_run")
                    self.assertEqual(result["effects_observed"]["calls"], [])
        runner.assert_not_called()
        default = execute({"steps": steps})
        self.assertNotIn("effects_observed", default["results"][0])

    def test_unreadable_large_and_symlink_samples_remain_unknown(self):
        path = self.root / "large"
        path.write_bytes(b"123")
        with patch("skills.capabilities.observations.MAX_FILE_BYTES", 2):
            self.assertEqual(file_state(path)["state"], "unknown")
        with patch.object(Path, "lstat", side_effect=PermissionError):
            self.assertEqual(file_state(path)["state"], "unknown")
        link = self.root / "link"
        try:
            link.symlink_to(path)
        except (OSError, NotImplementedError):
            return  # Windows may lack symlink privilege; other assertions still ran.
        self.assertEqual(file_state(link)["state"], "unknown")

    def test_bad_checkpoint_references_and_forged_comparisons_are_rejected(self):
        from skills.llm_backends import registry
        with ObservationSession() as session:
            registry.save(self.backends)
        report = session.report
        for mutate in (
            lambda r: r["calls"][0].update(parent_id="c1"),
            lambda r: r["observations"][0].update(call_id="absent"),
            lambda r: r["observations"][0].update(comparison="deviation"),
            lambda r: r["observations"][0].update(effect_ref="/expected_effects/999"),
            lambda r: r["declarations"][next(iter(r["declarations"]))].update(contract_version="forged"),
            lambda r: r.update(schema="botte.effect-observations/v999"),
        ):
            bad = deepcopy(report)
            mutate(bad)
            self.assertTrue(validate_report(bad))
        path = self.root / "checkpoint.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        self.assertTrue(read_checkpoint(path, "0" * 32)["problems"])
        path.write_text('{"schema": "a", "schema": "b"}', encoding="utf-8")
        self.assertTrue(read_checkpoint(path, report["run_id"])["problems"])


class ChildObservationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        # A synthetic installed toolkit tests the real subprocess transport with
        # no discovery, user config or host state. Production modules above are
        # exercised separately by the nested-call tests.
        for package in ("", "capabilities", "conductor", "llm_backends"):
            directory = self.root / "skills" / package
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "__init__.py").write_text("", encoding="utf-8")
        for relative in ("atomic_json.py", "capabilities/effects.py", "capabilities/observations.py",
                         "capabilities/observation_schema.py", "capabilities/network_observations.py",
                         "conductor/observed_run.py"):
            shutil.copyfile(REPO / "skills" / relative, self.root / "skills" / relative)
        (self.root / "skills/capabilities/registry.py").write_text(
            "from pathlib import Path\nREPO_ROOT = Path(__file__).resolve().parents[2]\n", encoding="utf-8")
        skill = self.root / "skills/llm_backends"
        (skill / "SKILL.md").write_text("fixture", encoding="utf-8")
        (skill / "cli.py").write_text(
            "import sys, time\nfrom pathlib import Path\n"
            "from skills.capabilities.observations import observed_operation, observed_file_write\n"
            "@observed_operation('fixture_write')\n"
            "def work():\n"
            "    with observed_file_write(Path('written.txt'), '/expected_effects/0'):\n"
            "        Path('written.txt').write_text('preuve', encoding='utf-8')\n"
            "    if sys.argv[-1] == 'timeout': time.sleep(10)\n"
            "    print('fixture output')\n"
            "    if sys.argv[-1] == 'failed': raise SystemExit(7)\n"
            "work()\n", encoding="utf-8")
        contract = contract_template(skill, "zedarvates/botte-secrete:skills/llm_backends")
        import hashlib
        contract["source_hashes"]["cli.py"] = hashlib.sha256((skill / "cli.py").read_bytes()).hexdigest()
        (skill / "effects.json").write_text(json.dumps(contract), encoding="utf-8")

    def test_subprocess_output_exit_code_and_declaration_evidence_round_trip(self):
        for mode, expected in (("ok", 0), ("failed", 7)):
            code, output, report = run_observed(f"python -m skills.llm_backends.cli {mode}",
                                                 str(self.root), 10)
            self.assertEqual(code, expected, output)
            self.assertIn("fixture output", output)
            self.assertEqual(report["process"], {"status": "exited", "exit_code": expected})
            self.assertEqual(validate_report(report), [])
            self.assertEqual(report["observations"][0]["comparison"], "supported")
            self.assertEqual(report["calls"][1]["parent_id"], report["calls"][0]["id"])
            self.assertEqual(report["calls"][0]["status"], "returned" if expected == 0 else "raised")

    def test_timeout_keeps_completed_write_and_unfinished_call_evidence(self):
        code, _, report = run_observed("python -m skills.llm_backends.cli timeout", str(self.root), 1)
        self.assertEqual(code, -1)
        self.assertEqual(report["process"]["status"], "timed_out")
        self.assertEqual(report["observations"][0]["after"]["state"], "present")
        self.assertEqual(summarize(report)["unfinished_calls"], 2)
        self.assertTrue(report["problems"])
        self.assertEqual(validate_report(report), [])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__, fromlist=["*"]))
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
