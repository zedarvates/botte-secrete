"""Observable evidence for discovery, scheduling and inherited audit effects.

Real file writes stay in a temporary tree; endpoint discovery and hardware
profiling are fixtures. These checks do not validate remote task completion.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from skills.llm_backends import registry
from skills.llm_backends.audit import Hardware, audit
from skills.llm_backends.discovery import Backend


class OperationEffectsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.registry_path = self.root / "registry.json"
        self.backends = [Backend("fixture", "fixture", "127.0.0.1", port,
                                 "openai", True, ["fixture-model"], 1,
                                 f"http://127.0.0.1:{port}") for port in (1234, 1235)]
        self.addCleanup(patch.stopall)
        patch.object(registry, "DEFAULT_REGISTRY_PATH", self.registry_path).start()
        self.discovery = patch.object(registry, "discover", return_value=self.backends).start()
        hardware = Hardware("fixture", "fixture", 4, 8.0)
        # Python 3.10's dotted mock resolver sees the re-exported audit function.
        patch.object(import_module("skills.llm_backends.audit"),
                     "profile_hardware", return_value=hardware).start()
        patch.object(import_module("skills.infra_advisor.advisor"),
                     "profile_hardware", return_value=hardware).start()
        patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network call")).start()

    def test_audit_cache_miss_and_fresh_replace_registry_but_cached_read_does_not(self):
        audit()
        self.discovery.assert_called_once()
        self.assertEqual(len(registry.load()), 2)
        saved = self.registry_path.read_bytes()
        self.discovery.reset_mock()
        audit()
        self.discovery.assert_not_called()
        self.assertEqual(self.registry_path.read_bytes(), saved)
        self.discovery.return_value = []
        audit(fresh=True)
        self.discovery.assert_called_once()
        self.assertEqual(registry.load(), [])
        self.assertNotEqual(self.registry_path.read_bytes(), saved)

    def test_cluster_status_updates_lru_without_delegating_work(self):
        from skills.cluster import cluster
        state_path = self.root / "lru.json"
        with patch.object(cluster, "_STATE", state_path), patch.object(cluster, "delegate") as delegate:
            first = cluster.status(scan_subnet=True)
            self.assertTrue(self.discovery.call_args.kwargs["scan_subnet"])
            self.assertEqual(len(json.loads(state_path.read_text(encoding="utf-8"))["last_used"]), 1)
            self.discovery.reset_mock()
            second = cluster.status()
        self.discovery.assert_not_called()
        delegate.assert_not_called()
        self.assertNotEqual(first["recommended_lru"]["port"], second["recommended_lru"]["port"])
        self.assertEqual(len(json.loads(state_path.read_text(encoding="utf-8"))["last_used"]), 2)

    def test_infra_cache_miss_writes_and_cli_tips_forces_refresh(self):
        from skills.infra_advisor.advisor import gather
        from skills.infra_advisor.cli import main
        gather(project=self.root)
        self.discovery.assert_called_once()
        self.assertTrue(self.registry_path.exists())
        self.discovery.reset_mock()
        gather(project=self.root, scan_subnet=True)
        self.discovery.assert_not_called()  # subnet does not force the cached gather path
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["tips", "--subnet", "--json"])
        self.assertEqual(code, 0)
        self.discovery.assert_called_once()
        self.assertTrue(self.discovery.call_args.kwargs["scan_subnet"])

    def test_checkup_inherits_registry_write_and_pr_comment_does_not_save(self):
        from skills.checkup.cli import run, main
        project = self.root / "project"
        (project / ".botte").mkdir(parents=True)
        (project / ".botte" / "policy.md").write_text("fixture", encoding="utf-8")
        (project / "app.py").write_text("value = 1\n", encoding="utf-8")
        host = {"total_prefix_tokens": 0, "breakdown": {"host": 0, "host_pct": 0},
                "components": {"host_skill_catalog": 0}, "counts": {"host_skills": 0},
                "reducible_tokens": 0}
        with patch("skills.context_profiler.profile_host", return_value=host):
            result = run(project)
        self.discovery.assert_called_once()
        self.assertEqual(len(registry.load()), 2)
        self.assertTrue(result["policy_committed"])  # existence, even without a Git repository
        result["drift"] = ["fixture drift"]
        with patch("skills.checkup.cli.run", return_value=result), patch("skills.report.save") as save:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = main([str(project), "--pr-comment", "--save", "both"])
        save.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("fixture drift", output.getvalue())


def main() -> int:
    result = unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OperationEffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
