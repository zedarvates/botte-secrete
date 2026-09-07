"""Behavior and compatibility checks for optional effects declarations."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.capabilities import load
from skills.capabilities.cli import main as cli
from skills.capabilities.effects import (
    MAX_CONTRACT_BYTES, contract_template, inspect_effects, validate_contract,
)


class EffectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skill = self.root / "sample"
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text(
            "---\nname: sample\ndescription: example\n---\n", encoding="utf-8")
        self.contract = contract_template(self.skill, "example/repo:skills/sample")

    def save(self, contract=None):
        (self.skill / "effects.json").write_text(
            json.dumps(self.contract if contract is None else contract), encoding="utf-8")

    def inspect(self):
        return inspect_effects(self.skill, expected_id="example/repo:skills/sample")

    def discover(self):
        return load(self.root, include_effects=True, capability_namespace="example/repo:skills")

    def test_template_preserves_unknowns_and_does_not_write(self):
        self.assertEqual(validate_contract(self.contract), [])
        self.assertEqual(self.contract["expected_effects"][0]["likelihood"], "unknown")
        self.assertEqual(self.contract["reversibility"]["status"], "unknown")
        self.assertEqual(self.contract["retry"]["semantics"], "unknown")
        self.assertEqual(self.contract["reuse"][0]["status"], "exploratory")
        self.assertEqual(self.contract["analysis"]["evidence_refs"], [])
        self.assertEqual(list(self.skill.iterdir()), [self.skill / "SKILL.md"])

    def test_default_discovery_keeps_legacy_shape_and_never_reads_sidecars(self):
        self.save()
        with patch("skills.capabilities.effects.inspect_effects") as inspect:
            result = load(self.root)[0].to_dict()
        inspect.assert_not_called()
        self.assertEqual(set(result), {"name", "layer", "description", "path", "local_capable"})
        self.assertEqual(result["name"], "sample")

    def test_missing_and_declared_are_distinct_in_opt_in_discovery(self):
        self.assertEqual(self.discover()[0].effects["status"], "missing")
        self.save()
        report = self.discover()[0].to_dict()["effects"]
        self.assertEqual(report["status"], "declared")
        self.assertEqual(report["contract"], self.contract)

    def test_bound_implementation_changes_or_disappears_are_stale(self):
        source = self.skill / "worker.py"
        source.write_text("print('first')\n", encoding="utf-8")
        self.contract["source_hashes"]["worker.py"] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.save()
        self.assertEqual(self.inspect()["status"], "declared")
        source.write_text("print('second')\n", encoding="utf-8")
        self.assertEqual(self.inspect()["status"], "stale")
        source.unlink()
        self.assertEqual(self.inspect()["status"], "stale")

    def test_changed_skill_is_stale_without_hiding_the_declaration(self):
        self.save()
        (self.skill / "SKILL.md").write_text("changed", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["status"], "stale")
        self.assertTrue(result["errors"])
        self.assertEqual(result["contract"], self.contract)

    def test_invalid_json_does_not_break_discovery(self):
        for content in ("{", "[]", '{"schema":"a","schema":"b"}',
                        "[" * 1500 + "]" * 1500, " " * (MAX_CONTRACT_BYTES + 1)):
            with self.subTest(content=content[:40]):
                (self.skill / "effects.json").write_text(content, encoding="utf-8")
                result = self.discover()[0].effects
                self.assertEqual(result["status"], "invalid")
                self.assertNotIn("contract", result)

    def test_unknown_version_fields_and_malformed_nested_values_fail(self):
        variants = []
        for key, value in (("schema", "botte.capability-effects/v2"),
                           ("authority_granted", True), ("source_hashes", []),
                           ("expected_effects", []), ("retry", None), ("reuse", [3])):
            item = copy.deepcopy(self.contract)
            item[key] = value
            variants.append(item)
        item = copy.deepcopy(self.contract)
        item["expected_effects"][0]["likelihood"] = 0.99
        variants.append(item)
        for variant in variants:
            with self.subTest(contract=variant):
                self.save(variant)
                self.assertEqual(inspect_effects(self.skill)["status"], "invalid")

    def test_validated_reuse_requires_context_and_evidence(self):
        reuse = self.contract["reuse"][0]
        reuse["status"] = "validated_in_context"
        self.assertTrue(validate_contract(self.contract))
        reuse["validated_context"] = "Fixture inputs on version 1; local test only."
        self.assertTrue(validate_contract(self.contract))
        reuse["evidence_refs"] = ["fixture-run:1"]
        self.assertEqual(validate_contract(self.contract), [])
        # This only validates the declaration, not the evidence's truth.
        self.save()
        self.assertEqual(self.inspect()["status"], "declared")

    def test_escape_paths_are_invalid(self):
        for name in ("../other", "/etc/hosts", "C:\\other", "a/../other", "a//other"):
            with self.subTest(name=name):
                contract = copy.deepcopy(self.contract)
                contract["source_hashes"][name] = "0" * 64
                self.assertTrue(validate_contract(contract))

    def test_symlink_cannot_read_external_source_or_sidecar(self):
        outside = self.root / "outside.json"
        outside.write_text(json.dumps(self.contract), encoding="utf-8")
        link = self.skill / "linked.json"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.contract["source_hashes"]["linked.json"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        self.save()
        self.assertEqual(self.inspect()["status"], "stale")
        (self.skill / "effects.json").unlink()
        (self.skill / "effects.json").symlink_to(outside)
        self.assertEqual(inspect_effects(self.skill)["status"], "invalid")

    def test_cli_reports_status_and_template_without_writing(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["effects", str(self.skill), "--id", "example/repo:skills/sample"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "missing")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["template", str(self.skill), "--id", "example/repo:skills/sample"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), self.contract)
        self.assertFalse((self.skill / "effects.json").exists())
        self.save()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["effects", str(self.skill), "--id", "example/repo:skills/sample"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "declared")

    def test_repository_declarations_match_their_sources(self):
        skills_root = Path(__file__).parents[1]
        sidecars = sorted(skills_root.rglob("effects.json"))
        self.assertTrue(sidecars, "expected at least one pilot declaration")
        for sidecar in sidecars:
            with self.subTest(capability=sidecar.parent.relative_to(skills_root)):
                result = inspect_effects(sidecar.parent)
                self.assertEqual(result["status"], "declared", result.get("errors"))

    def test_identity_mismatch_is_invalid_even_with_matching_hashes(self):
        self.contract["capability_id"] = "another/repo:skills/unrelated"
        self.save()
        result = self.inspect()
        self.assertEqual(result["status"], "invalid")
        self.assertIn("capability_id", result["errors"][0])
        self.assertNotIn("contract", result)
        self.assertEqual(self.discover()[0].effects["status"], "invalid")

    def test_external_identity_must_come_from_the_caller(self):
        self.save()
        self.assertEqual(inspect_effects(self.skill)["status"], "invalid")
        self.assertEqual(self.inspect()["status"], "declared")

    def test_bundled_identity_is_resolved_from_the_path(self):
        leaf = self.root / "skills" / "sample"
        leaf.mkdir(parents=True)
        (leaf / "SKILL.md").write_bytes((self.skill / "SKILL.md").read_bytes())
        contract = contract_template(leaf, "zedarvates/botte-secrete:skills/sample")
        sidecar = leaf / "effects.json"
        sidecar.write_text(json.dumps(contract), encoding="utf-8")
        with patch("skills.capabilities.registry.REPO_ROOT", self.root):
            self.assertEqual(inspect_effects(leaf)["status"], "declared")
            contract["capability_id"] = "another/repo:skills/sample"
            sidecar.write_text(json.dumps(contract), encoding="utf-8")
            self.assertEqual(inspect_effects(leaf)["status"], "invalid")

    def test_effects_discovery_keeps_duplicate_basenames_without_extra_reads(self):
        for folder in ("a/worker", "b/worker"):
            leaf = self.root / folder
            leaf.mkdir(parents=True)
            (leaf / "SKILL.md").write_text("---\nname: worker\ndescription: fixture\n---\n",
                                           encoding="utf-8")
            contract = contract_template(leaf, "example/repo:skills/" + folder)
            (leaf / "effects.json").write_text(json.dumps(contract), encoding="utf-8")
        self.assertEqual(len(load(self.root)), 2)  # legacy basename deduplication
        with patch("skills.capabilities.effects.inspect_effects") as inspect:
            self.assertEqual(len(load(self.root, preserve_paths=True)), 3)
        inspect.assert_not_called()
        workers = [c for c in self.discover() if c.name == "worker"]
        self.assertEqual(len(workers), 2)
        self.assertEqual({c.effects["contract"]["capability_id"] for c in workers},
                         {"example/repo:skills/a/worker", "example/repo:skills/b/worker"})


def main() -> int:
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(EffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed - len(result.skipped)} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
