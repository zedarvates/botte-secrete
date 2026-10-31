"""Reproducible local pilots; backend discovery is a fixture, never a network probe."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from skills.atomic_json import write_json
from skills.conductor.test_verified import plan, step
from skills.conductor.verified import execute_verified


class PilotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.addCleanup(patch.stopall)
        patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network call")).start()

    def test_checkup_observes_inherited_registry_creation(self):
        from skills.checkup.cli import run
        from skills.llm_backends import registry
        from skills.llm_backends.audit import Hardware
        from skills.llm_backends.discovery import Backend
        project = self.root / "project"
        (project / ".botte").mkdir(parents=True)
        (project / ".botte" / "policy.md").write_text("fixture", encoding="utf-8")
        (project / "app.py").write_text("value = 1\n", encoding="utf-8")
        backend = Backend("fixture", "fixture", "127.0.0.1", 1234,
                          "openai", True, ["fixture-model"], 1, "http://127.0.0.1:1234")
        patch.object(registry, "DEFAULT_REGISTRY_PATH", self.root / "registry.json").start()
        discovery = patch.object(registry, "discover", return_value=[backend]).start()
        for module in ("skills.llm_backends.audit", "skills.infra_advisor.advisor"):
            patch.object(import_module(module), "profile_hardware", return_value=Hardware("fixture", "fixture", 4, 8.0)).start()
        host = {"total_prefix_tokens": 0, "breakdown": {"host": 0, "host_pct": 0},
                "components": {"host_skill_catalog": 0}, "counts": {"host_skills": 0}, "reducible_tokens": 0}
        patch("skills.context_profiler.profile_host", return_value=host).start()
        s = step("audit", capability="checkup", command="python -m skills.checkup.cli project",
                 ensures=[{"kind": "file_exists", "path": "audit.json"},
                          {"kind": "file_exists", "path": "registry.json"}])
        def runner(command, cwd, timeout):
            write_json(self.root / "audit.json", run(project))
            return 0, "checkup fixture complete"
        report = execute_verified(plan(s), cwd=str(self.root), confirm=True, runner=runner)
        self.assertTrue(report["complete"])
        self.assertEqual(report["results"][0]["changed_paths"], ["audit.json", "registry.json"])
        discovery.assert_called_once()
        self.assertEqual(len(registry.load()), 1)
        # Preserve evidence as observations, without upgrading a caller declaration.
        self.assertIsNone(report["results"][0]["effects_before"])

    def test_prefix_pruner_measures_bytes_and_preserves_required_context(self):
        from skills.prefix_pruner import pruner
        patch.object(pruner, "PREFIX_STORE", self.root / "prefix-state.json").start()
        redundant = "# Context\n" + "unused fixture background\n" * 20
        content = ("Task: rédiger en français.\n"
                   "<system>Authorized project: fixture only.</system>\n" + redundant +
                   "# Work\nRequired result: concise explanation.\n")
        original = self.root / "input.txt"
        original.write_text(content, encoding="utf-8")
        tree = pruner.PrefixTree()
        sid = hashlib.sha256(redundant.encode()).hexdigest()[:12]
        tree.register_section(sid, "context", redundant, len(redundant) // 4)
        tree.record_use(sid)
        for _ in range(4):
            tree.record_skip(sid)
        expected = content.replace(redundant, "")
        s = step("prune", capability="prefix-pruner", command="python -m skills.prefix_pruner.cli prune",
                 ensures=[{"kind": "file_sha256", "path": "output.txt",
                           "value": hashlib.sha256(expected.encode()).hexdigest()},
                          {"kind": "text_contains", "path": "output.txt", "value": "Authorized project: fixture only."},
                          {"kind": "text_contains", "path": "output.txt", "value": "rédiger en français"}])
        s["observes"] = ["prefix-state.json"]
        s["requires"] = [{"kind": "file_exists", "path": "input.txt"}]
        s["source_hashes"] = {"input.txt": hashlib.sha256(content.encode()).hexdigest()}
        def runner(command, cwd, timeout):
            with contextlib.redirect_stderr(io.StringIO()):
                reduced = pruner.prune_content(original.read_text(encoding="utf-8"), tree, "aggressive")
            (self.root / "output.txt").write_text(reduced, encoding="utf-8")
            return 0, "pruned"
        report = execute_verified(plan(s), cwd=str(self.root), confirm=True, runner=runner)
        self.assertTrue(report["complete"])
        self.assertEqual(report["results"][0]["changed_paths"], ["output.txt", "prefix-state.json"])
        candidate_bytes = report["results"][0]["after"]["output.txt"]["bytes"]
        self.assertLess(candidate_bytes, len(content.encode()))
        self.assertEqual(original.read_text(encoding="utf-8"), content)

    def test_conductor_real_processes_resume_after_authorization_switch(self):
        worker = self.root / "worker.py"
        worker.write_text(
            "import sys\nfrom pathlib import Path\n"
            "p=Path(sys.argv[1]+'.txt')\n"
            "p.write_text(p.read_text(encoding='utf-8')+'done' if p.exists() else 'done', encoding='utf-8')\n",
            encoding="utf-8")
        first = step("first", command="python worker.py first")
        second = step("second", needs=["first"], command="python worker.py second")
        for s in (first, second):
            s["source_hashes"] = {"worker.py": hashlib.sha256(worker.read_bytes()).hexdigest()}
        p = plan(first, second)
        blocked = execute_verified(p, cwd=str(self.root), checkpoint="run.json")
        self.assertFalse(blocked["complete"])
        complete = execute_verified(p, cwd=str(self.root), checkpoint="run.json", resume=True, confirm=True)
        self.assertTrue(complete["complete"])
        reused = execute_verified(p, cwd=str(self.root), checkpoint="run.json", resume=True)
        self.assertTrue(reused["complete"])
        self.assertTrue(all(r["reused"] for r in reused["results"]))
        for name in ("first.txt", "second.txt"):
            self.assertEqual((self.root / name).read_text(encoding="utf-8"), "done")

    def test_machine_schemas_accept_generated_evidence_and_reject_unknown_fields(self):
        try:
            from jsonschema import Draft202012Validator, ValidationError
        except ImportError:
            self.skipTest("optional jsonschema test dependency unavailable")
        schemas = Path(__file__).resolve().parents[2] / "docs" / "schemas"
        validators = []
        for filename in ("skill-plan.schema.json", "skill-run.schema.json"):
            schema = json.loads((schemas / filename).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            validators.append(Draft202012Validator(schema))
        p = plan(step("work"))
        validators[0].validate(p)
        for kwargs in ({"dry_run": True}, {}, {"confirm": True, "runner": lambda *a: (0, "no file")}):
            validators[1].validate(execute_verified(p, cwd=str(self.root), **kwargs))
        (self.root / "input.txt").write_text("input", encoding="utf-8")
        first = step("first")
        first["requires"] = [{"kind": "file_sha256", "path": "input.txt",
                              "value": hashlib.sha256(b"input").hexdigest()}]
        reusable = plan(first, step("second", needs=["first"]))
        def runner(*args):
            for name in ("first.txt", "second.txt"):
                (self.root / name).write_text("done", encoding="utf-8")
            return 0, "ok"
        validators[1].validate(execute_verified(reusable, cwd=str(self.root), confirm=True,
                                                checkpoint="run.json", runner=runner))
        validators[1].validate(execute_verified(reusable, cwd=str(self.root),
                                                checkpoint="run.json", resume=True))
        (self.root / "input.txt").write_text("changed", encoding="utf-8")
        stale = execute_verified(reusable, cwd=str(self.root), checkpoint="run.json", resume=True)
        self.assertFalse(stale["complete"])
        validators[1].validate(stale)
        p["grant_authority"] = True
        with self.assertRaises(ValidationError):
            validators[0].validate(p)


def main():
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PilotTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed - len(result.skipped)} passed, {failed} failed, {len(result.skipped)} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
