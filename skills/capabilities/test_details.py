"""Progressive disclosure keeps complete selected values and revision boundaries."""

import contextlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from skills.capabilities.cli import main as cli
from skills.capabilities.effects import contract_template, inspect_effects
from skills.capabilities.observations import digest
from skills.capabilities.review import before, read_bundled_details, read_details


class DetailTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.skill = self.repo / "skills" / "worker"
        self.contract = self.make_skill(self.skill, "zedarvates/botte-secrete:skills/worker")
        patcher = patch("skills.capabilities.registry.REPO_ROOT", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_skill(self, path, identity):
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text("---\nname: worker\ndescription: fixture\n---\n", encoding="utf-8")
        contract = contract_template(path, identity)
        contract["expected_effects"].append(deepcopy(contract["expected_effects"][0]))
        contract["expected_effects"][1]["effect"] = "Second effect with café and preserved whitespace.\n"
        contract["analysis"]["summary"] = "Unrequested fixture prose must stay in the sidecar."
        contract["reuse"] = []
        self.save(path, contract)
        return contract

    def save(self, path=None, contract=None):
        (path or self.skill).joinpath("effects.json").write_text(
            json.dumps(self.contract if contract is None else contract, ensure_ascii=False), encoding="utf-8")

    def test_selected_values_preserve_full_context_and_leave_sources_unchanged(self):
        original = (self.skill / "effects.json").read_bytes()
        prior = before(inspect_effects(self.skill), source="skills/worker/SKILL.md")
        with patch("socket.socket.connect", side_effect=AssertionError("unexpected network")), \
             patch("subprocess.run", side_effect=AssertionError("unexpected execution")):
            report = read_details(self.skill, ["/expected_effects/1", "/retry", "/retry"],
                                  expected_sha256=prior["declaration_sha256"])
        self.assertEqual(report["selection_status"], "selected")
        self.assertTrue(report["matches_expected"])
        self.assertEqual(report["selected"], {"/expected_effects/1": self.contract["expected_effects"][1],
                                               "/retry": self.contract["retry"]})
        self.assertNotIn("Unrequested fixture prose", json.dumps(report))
        report["selected"]["/retry"]["semantics"] = "changed locally"
        self.assertEqual((self.skill / "effects.json").read_bytes(), original)

    def test_empty_section_is_available_and_not_a_claim_of_no_effects(self):
        report = read_details(self.skill, ["/reuse", "/required_scope"])
        self.assertEqual(report["selection_status"], "selected")
        self.assertEqual(report["selected"]["/reuse"], [])
        self.assertEqual(report["selected"]["/required_scope"], self.contract["required_scope"])
        self.assertIsNone(report["matches_expected"])

    def test_invalid_selectors_are_rejected_before_inspection(self):
        bad = [None, {}, "/retry", [], [True], ["/retry"] * 17,
               ["/"], ["/source_hashes"], ["/retry/0"], ["/analysis/summary"],
               ["/expected_effects/-1"], ["/expected_effects/01"], ["/expected_effects/*"],
               ["/expected_effects/9999999999"], ["/expected_effects/0/effect"],
               ["/preconditions/"], ["retry"], ["/" + "x" * 65]]
        with patch("skills.capabilities.review.inspect_effects") as inspect:
            for selectors in bad:
                with self.subTest(selectors=selectors), self.assertRaises(ValueError):
                    read_details(self.skill, selectors)
        inspect.assert_not_called()

    def test_invalid_digest_is_rejected_before_inspection(self):
        with patch("skills.capabilities.review.inspect_effects") as inspect:
            for value in ("", "0" * 63, "A" * 64, [], False, 123):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    read_details(self.skill, ["/retry"], expected_sha256=value)
        inspect.assert_not_called()

    def test_changed_declaration_returns_no_fragments_until_reference_refreshed(self):
        old = digest(self.contract)
        self.contract["retry"]["stop_condition"] = "New fixture condition"
        self.save()
        report = read_details(self.skill, ["/retry"], expected_sha256=old)
        self.assertEqual(report["status"], "declared")
        self.assertEqual(report["selection_status"], "changed")
        self.assertFalse(report["matches_expected"])
        self.assertEqual(report["selected"], {})
        current = read_details(self.skill, ["/retry"], expected_sha256=report["declaration_sha256"])
        self.assertEqual(current["selected"]["/retry"], self.contract["retry"])

    def test_json_formatting_does_not_change_the_canonical_digest(self):
        original = digest(self.contract)
        (self.skill / "effects.json").write_text(json.dumps(self.contract, sort_keys=True, indent=4), encoding="utf-8")
        report = read_details(self.skill, ["/expected_effects/1"], expected_sha256=original)
        self.assertEqual(report["selection_status"], "selected")
        self.assertTrue(report["matches_expected"])

    def test_stale_missing_and_invalid_sources_do_not_supply_fragments(self):
        expected = digest(self.contract)
        (self.skill / "SKILL.md").write_text("changed implementation", encoding="utf-8")
        stale = read_details(self.skill, ["/retry"], expected_sha256=expected)
        self.assertEqual(stale["status"], "stale")
        self.assertTrue(stale["matches_expected"])
        self.assertGreater(stale["error_count"], 0)
        self.assertEqual(stale["selected"], {})
        for content, status in (("{", "invalid"), (None, "missing")):
            sidecar = self.skill / "effects.json"
            if content is None:
                sidecar.unlink()
            else:
                sidecar.write_text(content, encoding="utf-8")
            report = read_details(self.skill, ["/retry"])
            self.assertEqual(report["status"], status)
            self.assertEqual(report["selected"], {})

    def test_missing_index_rejects_the_whole_selection(self):
        report = read_details(self.skill, ["/retry", "/expected_effects/99", "/reuse/0"])
        self.assertEqual(report["selection_status"], "not_found")
        self.assertEqual(report["selected"], {})
        self.assertEqual(report["missing_selectors"], ["/expected_effects/99", "/reuse/0"])

    def test_external_tree_requires_independent_identity(self):
        external = self.root / "external" / "worker"
        identity = "fixture/repository:skills/worker"
        self.make_skill(external, identity)
        self.assertEqual(read_details(external, ["/retry"])["status"], "invalid")
        report = read_details(external, ["/retry"], expected_id=identity)
        self.assertEqual(report["selection_status"], "selected")
        self.assertEqual(read_details(external, ["/retry"], expected_id="wrong/id")["selected"], {})

    def test_bundled_homonyms_are_distinct_and_source_spelling_is_constrained(self):
        other = self.repo / "skills" / "vendor" / "worker"
        identity = "zedarvates/botte-secrete:skills/vendor/worker"
        self.make_skill(other, identity)
        report = read_bundled_details("skills/vendor/worker/SKILL.md", ["/retry"])
        self.assertEqual(report["capability_id"], identity)
        report = read_bundled_details("skills/vendor/worker/SKILL.md", ["/retry"], expected_sha256=digest(self.contract))
        self.assertEqual(report["selection_status"], "changed")
        with patch("skills.capabilities.review.inspect_effects") as inspect:
            for source in (str(self.skill / "SKILL.md"), "worker", "skills/../outside/SKILL.md",
                           "skills//worker/SKILL.md", "skills/./worker/SKILL.md", "skills/worker/effects.json",
                           "skills\\worker\\SKILL.md", "C:/worker/SKILL.md", None):
                with self.subTest(source=source), self.assertRaises(ValueError):
                    read_bundled_details(source, ["/retry"])
        inspect.assert_not_called()

    def test_directory_and_sidecar_symlinks_cannot_disclose_external_fragments(self):
        external = self.root / "external"
        self.make_skill(external, "fixture/repository:skills/external")
        alias = self.repo / "skills" / "alias"
        try:
            alias.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with patch("skills.capabilities.review.inspect_effects") as inspect, self.assertRaises(ValueError):
            read_bundled_details("skills/alias/SKILL.md", ["/retry"])
        inspect.assert_not_called()
        alias.unlink()
        alias.symlink_to(self.skill, target_is_directory=True)
        with self.assertRaises(ValueError):
            read_bundled_details("skills/alias/SKILL.md", ["/retry"])
        sidecar = self.skill / "effects.json"
        sidecar.unlink()
        sidecar.symlink_to(external / "effects.json")
        self.assertEqual(read_bundled_details("skills/worker/SKILL.md", ["/retry"])["selected"], {})

    def test_mcp_lazy_discovery_and_dispatch_return_only_requested_details(self):
        from skills.llm_mcp.lazy import find_tool, lazy_tool_list
        from skills.llm_mcp.server import TOOLS, handle
        self.assertNotIn("effect_details", {t["name"] for t in lazy_tool_list(TOOLS)})
        match = find_tool("effect_details", TOOLS)["matches"][0]
        self.assertEqual(match["name"], "effect_details")
        self.assertIn("inputSchema", match)
        args = {"source": "skills/worker/SKILL.md", "selectors": ["/retry"], "expected_sha256": digest(self.contract)}
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "effect_details", "arguments": args}}
        response = handle(request)
        self.assertFalse(response["result"].get("isError", False))
        report = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(report["selected"], {"/retry": self.contract["retry"]})
        args["expected_id"] = "untrusted identity"
        self.assertTrue(handle(request)["result"]["isError"])

    def test_cli_preserves_legacy_output_and_reports_selection_failures(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["effects", str(self.skill)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["contract"], self.contract)
        for flags, expected in ((["--select", "/retry"], 0),
                                (["--select", "/retry", "--expect-sha256", "0" * 64], 1),
                                (["--select", "/reuse/0"], 1)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli(["effects", str(self.skill), *flags]), expected)
            self.assertNotIn("contract", json.loads(output.getvalue()))
        for flags in (["--select", "/retry/0"], ["--expect-sha256", "0" * 64]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli(["effects", str(self.skill), *flags])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DetailTests))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
