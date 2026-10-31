"""Regression checks for local diagnostics and non-activating candidate training."""

from __future__ import annotations

import json
import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from skills.botte_nn import active_learning as learning
from skills.checkup.cli import _nn_summary


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "ledger"
        self.models_dir = self.root / "source" / "models"
        self.models_dir.mkdir(parents=True)
        self.model_path = self.models_dir / "binary_router.json"
        self.model_path.write_text(json.dumps({
            "layers": [3, 2], "activations": ["softmax"],
            "weights": [[0.0] * 6], "biases": [[0.0, 0.0]],
            "trained_on": "test-fixture-source", "eval_accuracy": 0.123,
        }), encoding="utf-8")
        # The historical trainer derives its destination from __file__.
        # Isolate that path too, so the regression probe cannot replace repo weights.
        module_copy = self.root / "source" / "active_learning.py"
        module_copy.write_bytes(Path(learning.__file__).read_bytes())
        for name, value in (("DATA_DIR", self.data_dir),
                            ("MODELS_DIR", self.models_dir),
                            ("__file__", str(module_copy))):
            context = patch.object(learning, name, value)
            context.start()
            self.addCleanup(context.stop)

    def write_rows(self, count=80):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for index in range(count):
            label = index % 2
            rows.append(asdict(learning.InferenceLog(
                model_name="binary_router",
                features=[0.05 + index * 0.001 + label * 0.75, 1.0, 1.0],
                predicted_class=0, actual_class=label, correct=label == 0,
                timestamp=1_700_000_000.0 + index, verified=True,
                inference_id=f"fixture-{index}", outcome="explicit_feedback",
            )))
        self.ledger_path = self.data_dir / "inference_logs.jsonl"
        self.ledger_path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        return rows

    def test_status_does_not_create_missing_ledger_directory(self):
        report = learning.ActiveLearning().status()
        self.assertFalse(self.data_dir.exists())
        self.assertEqual(report["ledger_state"], "missing")

    def test_improved_training_preserves_source_model(self):
        self.write_rows()
        before = self.model_path.read_bytes()
        learner = learning.ActiveLearning()
        score = learner.train("binary_router", epochs=300, lr=0.15, verbose=False)
        self.assertEqual(self.model_path.read_bytes(), before)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0.5)
        self.assertTrue(learner.candidate_paths["binary_router"].is_file())

    def test_checkup_sample_count_never_grants_activation(self):
        fake_status = {
            "models": {"binary_router": {
                "observations": 0, "with_outcome": 2000,
                "unique_verified": 2000,
            }},
            "storage": "fixture-ledger", "ledger_state": "present",
            "invalid_rows": 0,
        }
        with patch.object(learning.ActiveLearning, "status", return_value=fake_status):
            summary = _nn_summary(Path(__file__).resolve().parents[2])
        self.assertFalse(summary["learning"]["activation_ready"])
        self.assertTrue(summary["learning"]["activation_sample_ready"])

    def replace_rows(self, rows):
        self.ledger_path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def test_empty_invalid_and_unreadable_are_distinct(self):
        self.write_rows(0)
        self.assertEqual(learning.ActiveLearning().status()["ledger_state"], "empty")
        self.ledger_path.write_text('{"unfinished":', encoding="utf-8")
        invalid = learning.ActiveLearning().status()
        self.assertEqual((invalid["ledger_state"], invalid["invalid_rows"]), ("invalid", 1))
        with patch.object(Path, "read_bytes", side_effect=PermissionError("fixture")):
            self.assertEqual(learning.ActiveLearning().status()["ledger_state"], "unreadable")

    def test_status_cli_needs_no_numpy_and_creates_no_files(self):
        result = subprocess.run([
            sys.executable, "-S", "-m", "skills.botte_nn.active_learning", "status",
            "--json", "--data-dir", str(self.data_dir),
        ], cwd=Path(__file__).resolve().parents[2], capture_output=True,
            text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["ledger_state"], "missing")
        self.assertEqual(report["measurement_scope"], "selected_local_ledger_only")
        self.assertEqual(Path(report["storage"]), self.data_dir / "inference_logs.jsonl")
        self.assertFalse(self.data_dir.exists())

    def test_current_baseline_and_source_bound_candidate(self):
        rows = self.write_rows()
        # Historical predictions claim perfection. The pinned source is only
        # 50% correct on this fixture, which must be measured again before fitting.
        for row in rows:
            row.update(predicted_class=row["actual_class"], correct=True)
        self.replace_rows(rows)
        source = self.model_path.read_bytes()
        ledger = self.ledger_path.read_bytes()
        learner = learning.ActiveLearning()
        self.assertGreater(learner.train("binary_router", epochs=300, lr=0.15, verbose=False), 0.5)
        candidate = json.loads(learner.candidate_paths["binary_router"].read_text(encoding="utf-8"))
        proof = candidate["provenance"]
        self.assertEqual(proof["source_validation_accuracy"], 0.5)
        self.assertEqual(proof["source_model_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(proof["ledger_sha256"], hashlib.sha256(ledger).hexdigest())
        self.assertEqual(proof["source_metadata"]["trained_on"], "test-fixture-source")
        self.assertEqual(proof["source_metadata"]["eval_accuracy"], 0.123)
        self.assertFalse(proof["activation_allowed"])
        self.assertFalse(proof["source_weights_replaced"])
        self.assertEqual(proof["split"]["train_count"], 64)
        self.assertEqual(proof["split"]["validation_count"], 16)
        self.assertEqual(proof["split"]["cutoff_timestamp"], rows[64]["timestamp"])
        self.assertEqual(proof["split"]["validation_classes"], {"0": 8, "1": 8})
        self.assertEqual(set(proof["code_sha256"]), {"features", "trainer", "active_learning"})
        self.assertEqual(self.ledger_path.read_bytes(), ledger)
        self.assertEqual(self.model_path.read_bytes(), source)

    def test_repeated_exports_preserve_previous_candidates(self):
        self.write_rows()
        learner = learning.ActiveLearning()
        learner.train("binary_router", epochs=300, lr=0.15, verbose=False)
        first = learner.candidate_paths["binary_router"]
        before = first.read_bytes()
        learner.train("binary_router", epochs=300, lr=0.15, verbose=False)
        self.assertNotEqual(first, learner.candidate_paths["binary_router"])
        self.assertEqual(first.read_bytes(), before)

    def test_fewer_than_50_verdicts_creates_no_candidate(self):
        self.write_rows(49)
        learner = learning.ActiveLearning()
        self.assertIsNone(learner.train("binary_router", verbose=False))
        self.assertFalse((self.data_dir / "candidates").exists())

    def test_unverified_observations_never_train(self):
        rows = self.write_rows()
        for row in rows:
            row.update(verified=False, actual_class=None, correct=None)
        self.replace_rows(rows)
        learner = learning.ActiveLearning()
        self.assertEqual(learner.status()["observations"], 80)
        self.assertIsNone(learner.train("binary_router", verbose=False))
        self.assertFalse((self.data_dir / "candidates").exists())

    def test_duplicates_and_conflicting_inputs_do_not_fill_sample_gate(self):
        rows = self.write_rows()
        for row in rows:
            row.update(features=[0.2, 1.0, 1.0], actual_class=0, correct=True)
        self.replace_rows(rows)
        learner = learning.ActiveLearning()
        counts = learner.status()["models"]["binary_router"]
        self.assertEqual((counts["with_outcome"], counts["unique_verified"]), (80, 1))
        self.assertIsNone(learner.train("binary_router", verbose=False))
        rows[-1].update(actual_class=1, correct=False)
        self.replace_rows(rows)
        counts = learner.status()["models"]["binary_router"]
        self.assertEqual((counts["unique_verified"], counts["conflicting_inputs"]), (0, 1))

    def test_incompatible_classes_shapes_and_temporal_sets_are_rejected(self):
        for kind in ("shape", "class", "single_class", "same_time"):
            with self.subTest(kind=kind):
                rows = self.write_rows()
                for row in rows:
                    if kind == "shape":
                        row["features"] = row["features"][:2]
                    elif kind == "class":
                        row.update(actual_class=2, correct=False)
                    elif kind == "single_class":
                        row.update(actual_class=0, correct=True)
                    else:
                        row["timestamp"] = 1_700_000_000.0
                self.replace_rows(rows)
                with self.assertRaises(ValueError):
                    learning.ActiveLearning().train("binary_router", verbose=False)
                self.assertFalse((self.data_dir / "candidates").exists())

    def test_invalid_rows_are_visible_and_stop_training(self):
        for change in ({"verified": "true"}, {"confidence": float("nan")},
                       {"timestamp": 10 ** 400}, {"actual_class": -1}, {"correct": 1}):
            with self.subTest(change=str(change)[:70]):
                rows = self.write_rows()
                rows[0].update(change)
                self.replace_rows(rows)
                learner = learning.ActiveLearning()
                self.assertEqual(learner.status()["ledger_state"], "invalid")
                with self.assertRaises(ValueError):
                    learner.train("binary_router", verbose=False)
                self.assertFalse((self.data_dir / "candidates").exists())

    def test_invalid_cli_diagnostic_returns_error_without_rewriting_ledger(self):
        self.write_rows()
        self.ledger_path.write_bytes(b"\xff")
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(learning.main(["status", "--json"]), 2)
        self.assertEqual(json.loads(output.getvalue())["ledger_state"], "invalid")
        self.assertEqual(self.ledger_path.read_bytes(), b"\xff")

    def test_no_improvement_exports_nothing(self):
        self.write_rows()
        learner = learning.ActiveLearning()
        learner.train("binary_router", epochs=300, lr=0.15, verbose=False)
        self.model_path.write_bytes(learner.candidate_paths["binary_router"].read_bytes())
        before = self.model_path.read_bytes()
        output = self.root / "no-improvement"
        self.assertIsNone(learner.train("binary_router", epochs=1, verbose=False, output_dir=output))
        self.assertFalse(output.exists())
        self.assertEqual(self.model_path.read_bytes(), before)

    def test_source_output_and_model_traversal_are_rejected(self):
        self.write_rows()
        learner = learning.ActiveLearning()
        for destination in (self.models_dir, self.models_dir / "nested"):
            with self.assertRaises(ValueError):
                learner.train("binary_router", output_dir=destination, verbose=False)
        with self.assertRaises(ValueError):
            learner.train("../binary_router", verbose=False)

    def test_rebuild_stops_before_loading_training_or_subprocess(self):
        with patch.object(learning, "ActiveLearning") as constructor, \
                patch("subprocess.run") as process, patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as raised:
                learning.main(["rebuild"])
        self.assertEqual(raised.exception.code, 2)
        constructor.assert_not_called()
        process.assert_not_called()

    def test_failed_candidate_write_preserves_source_and_leaves_no_final_artifact(self):
        self.write_rows()
        before = self.model_path.read_bytes()
        output = self.root / "write-failure"
        with patch.object(learning.os, "replace", side_effect=OSError("fixture write failure")):
            with self.assertRaises(OSError):
                learning.ActiveLearning().train(
                    "binary_router", epochs=300, lr=0.15, verbose=False, output_dir=output
                )
        self.assertEqual(self.model_path.read_bytes(), before)
        self.assertEqual(list(output.iterdir()), [])

    def test_malformed_source_cannot_fall_back_to_random_initialization(self):
        self.write_rows()
        source = json.loads(self.model_path.read_text(encoding="utf-8"))
        source["weights"] = []
        self.model_path.write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaises(ValueError):
            learning.ActiveLearning().train("binary_router", verbose=False)
        self.assertFalse((self.data_dir / "candidates").exists())


def main():
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests)
    )
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
