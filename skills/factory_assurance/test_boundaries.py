"""Regression tests for verdict, identity and public-output boundaries."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from skills.capabilities.observations import empty_report, validate_report

from .adapters import effect_manifest_to_assurance, holdout_attestation, observation_to_effects
from .assurance import evaluate_assurance, load_run
from .mutations import mutate_assurance_record
from .private_holdout import PrivateHoldoutError, load_private_set, run_private_holdout
from .private_holdout_cli import main as holdout_main
from .test_factory_assurance import _fixture
from .test_integrations import _observation


class HoldoutBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "synthetic-holdout.json"
        self.marker = "PUBLIC-SYNTHETIC-TASK-été"
        self.case_id = "synthetic-case-not-in-public-output"
        self.path.write_text(json.dumps({
            "set_id": "public-fixture-v1", "cases": [{
                "id": self.case_id, "input": {"prompt": self.marker, "expected": True},
            }],
        }), encoding="utf-8")
        self.options = {"private_set_path": self.path, "candidate_sha": "a" * 40}

    def test_callback_requires_an_actual_boolean(self):
        for value in ("false", "true", 0, 1, None, {}, [False]):
            with self.subTest(value=value), self.assertRaises(PrivateHoldoutError):
                run_private_holdout(**self.options, evaluator=lambda case: value)
        for value, status in ((True, "pass"), (False, "fail")):
            self.assertEqual(run_private_holdout(
                **self.options, evaluator=lambda case: value)["status"], status)

    def test_attestation_does_not_coerce_verdict_or_count(self):
        valid = {"set_id": "public-fixture-v1", "digest": "b" * 64,
                 "candidate_sha": "a" * 40, "passed": True, "case_count": 1}
        for key, values in (("passed", ("false", 0, 1, None)),
                            ("case_count", (True, False, 1.0, "1", 0, -1)),
                            ("set_id", (None, 4, " ")),
                            ("digest", (None, 2, "x" * 64)),
                            ("candidate_sha", (None, 2, "x" * 40))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    holdout_attestation(**{**valid, key: value})

    def test_invalid_configuration_does_not_call_evaluator(self):
        for key, values in (("candidate_sha", (None, 1, "wrong", "g" * 40)),
                            ("timeout_seconds", (True, "1", 0, -1, float("nan"), float("inf")))):
            for value in values:
                callback = Mock(return_value=True)
                with self.subTest(key=key, value=value), self.assertRaises((ValueError, PrivateHoldoutError)):
                    run_private_holdout(**{**self.options, key: value}, evaluator=callback)
                callback.assert_not_called()
        with patch("skills.factory_assurance.private_holdout.subprocess.run") as dispatch:
            for argv in ([], "python", [""], [None], ["python", 3]):
                with self.subTest(argv=argv), self.assertRaises(PrivateHoldoutError):
                    run_private_holdout(**self.options, evaluator_argv=argv)
            dispatch.assert_not_called()

    def test_evaluator_protocol_is_closed_and_unambiguous(self):
        for response in ('{"passed":false,"passed":true}',
                         '{"passed":true,"details":"synthetic"}',
                         '{"passed":"false"}', '{"passed":1}',
                         '{"passed":NaN}', '{"passed":1e9999}', 'true', '[]', 'invalid'):
            completed = subprocess.CompletedProcess(["synthetic-evaluator"], 0, response, "")
            with self.subTest(response=response), patch(
                "skills.factory_assurance.private_holdout.subprocess.run", return_value=completed
            ), self.assertRaises(PrivateHoldoutError):
                run_private_holdout(**self.options, evaluator_argv=["synthetic-evaluator"])

    def test_private_input_rejects_duplicate_and_nonfinite_json(self):
        for payload in ('{"set_id":"first","set_id":"second","cases":[{"id":"x","input":1}]}',
                        '{"set_id":"x","cases":[{"id":"x","input":{"n":1,"n":2}}]}',
                        '{"set_id":"x","cases":[{"id":"x","input":NaN}]}',
                        '{"set_id":"x","cases":[{"id":"x","input":1e9999}]}'):
            self.path.write_text(payload, encoding="utf-8")
            with self.subTest(payload=payload), self.assertRaises(PrivateHoldoutError):
                load_private_set(self.path)

    def _cli(self, argv):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = holdout_main(argv)
        return status, output.getvalue(), errors.getvalue()

    def test_documented_cli_order_and_literal_evaluator_arguments(self):
        evaluator = [sys.executable, "-c", (
            "import json,sys; request=json.load(sys.stdin); "
            "print(json.dumps({'passed': request['input']['prompt']==sys.argv[1] "
            "and request['id']==sys.argv[2] and sys.argv[3]=='--candidate-sha'}))"
        ), self.marker, self.case_id, "--candidate-sha"]
        for options_first in (False, True):
            with self.subTest(options_first=options_first):
                destination = self.root / f"attestation-{options_first}.json"
                options = ["--candidate-sha", "a" * 40, "--output", str(destination)]
                prefix = options + [str(self.path)] if options_first else [str(self.path)] + options
                status, output, errors = self._cli(prefix + ["--"] + evaluator)
                self.assertEqual(status, 0, errors)
                attestation = json.loads(destination.read_text(encoding="utf-8"))
                self.assertEqual(attestation["status"], "pass")
                self.assertEqual(attestation["case_count"], 1)
                for stream in (output, errors, json.dumps(attestation, ensure_ascii=False)):
                    self.assertNotIn(self.marker, stream)
                    self.assertNotIn(self.case_id, stream)

    def test_cli_failures_do_not_publish_case_data(self):
        failures = [
            subprocess.CompletedProcess(["synthetic"], 3, self.marker, self.case_id),
            subprocess.CompletedProcess(["synthetic"], 0, self.marker, self.case_id),
            subprocess.TimeoutExpired(["synthetic"], 1, output=self.marker, stderr=self.case_id),
            OSError(self.marker + self.case_id),
        ]
        for failure in failures:
            destination = self.root / "not-created.json"
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=type(failure).__name__), patch(
                "skills.factory_assurance.private_holdout.subprocess.run", **kwargs
            ):
                status, output, errors = self._cli([
                    "--candidate-sha", "a" * 40, "--output", str(destination),
                    str(self.path), "--", "synthetic-evaluator",
                ])
            self.assertEqual(status, 2)
            self.assertFalse(destination.exists())
            self.assertEqual(output, "")
            self.assertTrue(errors)
            self.assertNotIn(self.marker, errors)
            self.assertNotIn(self.case_id, errors)

    def test_cli_does_not_overwrite_input(self):
        before = self.path.read_bytes()
        with patch("skills.factory_assurance.private_holdout.subprocess.run") as dispatch:
            status, _, _ = self._cli([
                str(self.path), "--candidate-sha", "a" * 40,
                "--output", str(self.path), "--", "synthetic-evaluator",
            ])
            self.assertEqual(status, 2)
            dispatch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)


class AssuranceBoundaryTests(unittest.TestCase):
    def test_effect_pointer_is_bound_to_its_declaration(self):
        manifest_path = Path(__file__).parents[1] / "capabilities" / "effects.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Two valid declarations deliberately reuse the same local pointer.
        other = deepcopy(manifest)
        other["capability_id"] = "botte:skills/different"
        other["downstream_effects"] = [deepcopy(other["expected_effects"][0])]
        report = _observation(other)
        report["network"] = []
        self.assertEqual(validate_report(report), [])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "other-observation.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            expected = effect_manifest_to_assurance(manifest_path)
            actual = observation_to_effects(path)
        self.assertTrue(actual["observed"])
        self.assertFalse(actual["unresolved"])
        self.assertTrue(set(actual["observed"]) - set(expected["declared"]))
        record = _fixture()
        record["effects"] = {"declared": expected["declared"], **actual}
        self.assertEqual(evaluate_assurance(record)["status"], "hold")

    def test_mutations_break_tree_equivalence_and_required_evidence(self):
        record = _fixture()
        record["identity"].update({"build_sha": "b" * 40, "tested_sha": "b" * 40,
                                  "source_tree": "c" * 40, "build_tree": "c" * 40,
                                  "tested_tree": "c" * 40})
        self.assertEqual(evaluate_assurance(record)["status"], "review_ready")
        self.assertEqual(evaluate_assurance(mutate_assurance_record(record, "identity-drift"))["status"], "hold")
        # A mutation must not accidentally restore direct commit equality.
        record["identity"].update({"source_sha": "b" * 40, "build_sha": "b" * 40, "tested_sha": "a" * 40})
        self.assertEqual(evaluate_assurance(record)["status"], "review_ready")
        self.assertEqual(evaluate_assurance(mutate_assurance_record(record, "identity-drift"))["status"], "hold")
        for all_optional in (False, True):
            record = _fixture()
            record["evidence"][0]["required"] = False
            if all_optional:
                record["evidence"][1]["required"] = False
            with self.subTest(all_optional=all_optional):
                self.assertEqual(evaluate_assurance(record)["status"], "review_ready")
                self.assertEqual(evaluate_assurance(mutate_assurance_record(record, "missing-evidence"))["status"], "hold")

    def test_identity_requires_git_hashes(self):
        for value in ("not-a-git-object", "g" * 40, 123, True, ["a" * 40]):
            record = _fixture()
            record["identity"].update({key: value for key in ("source_sha", "build_sha", "tested_sha")})
            with self.subTest(value=value):
                self.assertEqual(evaluate_assurance(record)["status"], "hold")
        record = _fixture()
        record["identity"].update({"build_sha": "b" * 40, "tested_sha": "b" * 40,
                                  "source_tree": "not-a-tree", "build_tree": "not-a-tree",
                                  "tested_tree": "not-a-tree"})
        self.assertEqual(evaluate_assurance(record)["status"], "hold")

    def test_malformed_record_is_held_instead_of_coerced(self):
        for key, values in (("mission", ([], "x", None)), ("actors", ([], "x", None)),
                            ("effects", ([], "x", None)), ("controls", ([], "x", None)),
                            ("identity", ([], "x", None)), ("schema_version", (True, 1.0)),
                            ("stage", ([], {})), ("requested_autonomy", ([], {}))):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertEqual(evaluate_assurance({**_fixture(), key: value})["status"], "hold")
        for value in (0, "false", [], None):
            record = _fixture()
            record["evidence"][0].update({"status": "fail", "required": value})
            with self.subTest(required=value):
                self.assertEqual(evaluate_assurance(record)["status"], "hold")
        for value in ("source", [["source"]], {"source": True}):
            record = _fixture()
            record["effects"].update({"declared": value, "observed": value})
            with self.subTest(effects=value):
                self.assertEqual(evaluate_assurance(record)["status"], "hold")

    def test_assurance_json_cannot_replace_a_failed_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ambiguous.json"
            path.write_text('{"status":"fail","status":"pass"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_run(path)

    def test_incomplete_or_failed_process_remains_unresolved(self):
        for status, code in (("launch_failed", None), ("runner_error", None),
                             ("timed_out", None), ("not_run", None),
                             ("running", None), ("exited", 1), ("exited", None)):
            report = empty_report("a" * 32)
            report["process"] = {"status": status, "exit_code": code}
            self.assertEqual(validate_report(report), [])
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "observation.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                adapted = observation_to_effects(path)
            with self.subTest(status=status, code=code):
                self.assertTrue(adapted["unresolved"])
                record = _fixture()
                record["effects"].update(adapted)
                self.assertEqual(evaluate_assurance(record)["status"], "hold")

    def test_adapter_rejects_invalid_upstream_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid-observation.json"
            path.write_text(json.dumps({"schema": "botte.effect-observations/v2",
                                       "observations": [], "network": [], "problems": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                observation_to_effects(path)


def main() -> int:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"\nRESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
