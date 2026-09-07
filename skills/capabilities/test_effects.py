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
        self.assertEqual(load(self.root, include_effects=True)[0].effects["status"], "missing")
        self.save()
        report = load(self.root, include_effects=True)[0].to_dict()["effects"]
        self.assertEqual(report["status"], "declared")
        self.assertEqual(report["contract"], self.contract)

    def test_bound_implementation_changes_or_disappears_are_stale(self):
        source = self.skill / "worker.py"
        source.write_text("print('first')\n", encoding="utf-8")
        self.contract["source_hashes"]["worker.py"] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.save()
        self.assertEqual(inspect_effects(self.skill)["status"], "declared")
        source.write_text("print('second')\n", encoding="utf-8")
        self.assertEqual(inspect_effects(self.skill)["status"], "stale")
        source.unlink()
        self.assertEqual(inspect_effects(self.skill)["status"], "stale")

    def test_changed_skill_is_stale_without_hiding_the_declaration(self):
        self.save()
        (self.skill / "SKILL.md").write_text("changed", encoding="utf-8")
        result = inspect_effects(self.skill)
        self.assertEqual(result["status"], "stale")
        self.assertTrue(result["errors"])
        self.assertEqual(result["contract"], self.contract)

    def test_invalid_json_does_not_break_discovery(self):
        for content in ("{", "[]", '{"schema":"a","schema":"b"}',
                        "[" * 1500 + "]" * 1500, " " * (MAX_CONTRACT_BYTES + 1)):
            with self.subTest(content=content[:40]):
                (self.skill / "effects.json").write_text(content, encoding="utf-8")
                result = load(self.root, include_effects=True)[0].effects
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
        self.assertEqual(inspect_effects(self.skill)["status"], "declared")

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
        self.assertEqual(inspect_effects(self.skill)["status"], "stale")
        (self.skill / "effects.json").unlink()
        (self.skill / "effects.json").symlink_to(outside)
        self.assertEqual(inspect_effects(self.skill)["status"], "invalid")

    def test_cli_reports_status_and_template_without_writing(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["effects", str(self.skill)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "missing")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["template", str(self.skill), "--id", "example/repo:skills/sample"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), self.contract)
        self.assertFalse((self.skill / "effects.json").exists())
        self.save()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["effects", str(self.skill)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "declared")

    def test_repository_pilot_matches_its_sources(self):
        result = inspect_effects(Path(__file__).parent)
        self.assertEqual(result["status"], "declared", result.get("errors"))


def main() -> int:
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(EffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed - len(result.skipped)} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
