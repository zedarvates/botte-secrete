"""Stdlib CLI contracts selected by the canonical test runner."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from .cli import main as cli_main
from .core import compare_github_inventory, summarize_registry, validate_registry


def fixture():
    return {"schema_version": 1, "programs": {"portfolio": [{
        "id": "sample", "source": "github:example/sample", "visibility": "private",
        "status": "archived", "priority": "high", "confidentiality": "restricted",
    }]}}


class PortfolioCliContracts(unittest.TestCase):
    def invoke(self, registry, observed, *, json_output=True, fail_on_drift=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry_path, observed_path = root / "registry.json", root / "observed.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            observed_path.write_text(json.dumps(observed), encoding="utf-8")
            before = registry_path.read_bytes(), observed_path.read_bytes()
            argv = ["diff", "--registry", str(registry_path), "--observed", str(observed_path)]
            if json_output:
                argv.append("--json")
            if fail_on_drift:
                argv.append("--fail-on-drift")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli_main(argv)
            self.assertEqual(before, (registry_path.read_bytes(), observed_path.read_bytes()))
            return code, out.getvalue(), err.getvalue()

    def test_invalid_observed_values_are_not_disclosed(self):
        marker = "PUBLIC-SYNTHETIC-DISCLOSURE-CANARY"
        for json_output in (False, True):
            with self.subTest(json_output=json_output):
                code, out, err = self.invoke(fixture(), [{"secret": marker}], json_output=json_output)
                self.assertEqual(code, 2)
                self.assertNotIn(marker, out + err)
                if json_output:
                    self.assertEqual(json.loads(out), {"valid": False, "error": "invalid_portfolio_input"})
                else:
                    self.assertEqual(err.strip(), "ERROR: invalid_portfolio_input")

    def test_invalid_schema_values_and_key_paths_are_not_disclosed(self):
        marker = "PUBLIC-SYNTHETIC-DISCLOSURE-CANARY"
        for source in ("schema", "location"):
            for json_output in (False, True):
                with self.subTest(source=source, json_output=json_output):
                    registry = fixture()
                    if source == "schema":
                        registry["schema_version"] = {"secret": marker}
                    else:
                        registry[marker] = {"password": "PUBLIC-SYNTHETIC-REJECTED-VALUE"}
                    code, out, err = self.invoke(registry, [], json_output=json_output)
                    self.assertEqual(code, 2)
                    self.assertNotIn(marker, out + err)
                    self.assertNotIn("PUBLIC-SYNTHETIC-REJECTED-VALUE", out + err)

    def test_validated_whitespace_has_consistent_summary_and_comparison(self):
        registry = fixture()
        row = registry["programs"].pop("portfolio")[0]
        registry["programs"][" portfolio "] = [{key: " " + value + " " for key, value in row.items()}]
        before = copy.deepcopy(registry)
        self.assertTrue(validate_registry(registry)["valid"])
        summary = summarize_registry(registry)
        self.assertEqual(summary["by_status"], {"archived": 1})
        self.assertEqual(summary["by_priority"], {"high": 1})
        self.assertEqual(summary["by_visibility"], {"private": 1})
        self.assertEqual(summary["by_confidentiality"], {"restricted": 1})
        self.assertEqual(summary["by_program"], {"portfolio": 1})
        self.assertEqual(summary["by_source_type"], {"github": 1})
        observed = [{"full_name": "example/sample", "private": True, "archived": True}]
        report = compare_github_inventory(registry, observed)
        self.assertTrue(report["clean"])
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["registered_github"], 1)
        self.assertEqual(registry, before)

    def test_cli_distinguishes_clean_inventory_and_visibility_drift(self):
        for private, expected in ((True, 0), (False, 1)):
            with self.subTest(private=private):
                code, out, err = self.invoke(fixture(), [{"full_name": "example/sample",
                    "private": private, "archived": True}], fail_on_drift=True)
                self.assertEqual(code, expected)
                self.assertEqual(err, "")
                report = json.loads(out)
                self.assertEqual(report["drift_count"], expected)
                self.assertEqual(report["clean"], not expected)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PortfolioCliContracts)
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"{result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
