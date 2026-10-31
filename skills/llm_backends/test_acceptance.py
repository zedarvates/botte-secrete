"""Synthetic transport tests for the portable kit, not homelab/GPU evidence."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.atomic_json import write_json
from skills.llm_backends import acceptance as kit
from skills.llm_backends.runtime_contract import load
from skills.llm_backends.test_runtime import engine, ready

ENGINE = {"os": "Linux", "gpu_probe": "observed", "devices": [
    {"id": "gpu-0", "name": "synthetic-gpu", "vram_mib": 12288, "free_vram_mib": 11000},
    {"id": "gpu-1", "name": "synthetic-gpu", "vram_mib": 12288, "free_vram_mib": 10000}]}
CONTROLLER = {"os": "Windows", "gpu_probe": "unavailable", "devices": []}


def echo(handler, body, result):
    result["choices"][0]["message"]["content"] = body["messages"][-1]["content"].rsplit(" ", 1)[-1]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.directory = self.root / "acceptance"
        self.engine_path = self.root / "engine.private.json"

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, url="http://127.0.0.1:8080/v1", memory="none"):
        config = ready(url, memory=memory)
        config["hosts"][0]["devices"] = [{"id": "gpu-0", "vram_mib": 12288}]
        config["profiles"][0]["device_ids"] = ["gpu-0"]
        config["budgets"]["max_output_tokens"] = 64
        return config

    def package(self, config):
        kit.prepare(config, self.directory)
        challenge = kit.challenge_at(self.directory / "challenge.json")
        with patch.object(kit, "host_identity", return_value="b" * 64), patch.object(kit, "inspect_local", return_value=ENGINE):
            record = kit.collect(challenge, "engine", self.root)
        write_json(self.engine_path, record)
        return record

    def run_kit(self, record_memory=False):
        with patch.object(kit, "host_identity", return_value="a" * 64), patch.object(kit, "inspect_local", return_value=CONTROLLER):
            return kit.run(self.directory, self.engine_path, record_memory=record_memory)

    def test_preparation_and_collection_are_offline_and_private(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            self.package(self.prepare())
        self.assertEqual(load(self.directory / "task.json")["verification"], "exact")
        with self.assertRaises(FileExistsError):
            kit.prepare(self.prepare(), self.directory)
        if os.name != "nt":
            self.assertEqual((self.directory / "config.private.json").stat().st_mode & 0o777, 0o600)

    def test_requires_direct_one_gpu_and_small_budget_before_any_write(self):
        configs = []
        config = self.prepare(); config["state"] = "draft"; configs.append(config)
        config = self.prepare(); config["profiles"][0]["device_ids"] = []; configs.append(config)
        config = self.prepare(); config["budgets"]["max_output_tokens"] = 512; configs.append(config)
        config = self.prepare(); config["budgets"]["timeout_seconds"] = 300; configs.append(config)
        config = self.prepare(); candidate = copy.deepcopy(config["profiles"][0]); candidate["id"] = "other"
        config["profiles"].append(candidate); config["fallback_profile"] = "other"; configs.append(config)
        for index, config in enumerate(configs):
            with self.subTest(index=index), self.assertRaises(ValueError):
                kit.prepare(config, self.directory)
            self.assertFalse(self.directory.exists())

    def test_same_installation_is_refused_before_inference(self):
        with engine(echo) as (url, requests):
            record = self.package(self.prepare(url))
            record["installation_token"] = "a" * 64; write_json(self.engine_path, record)
            with self.assertRaises(ValueError):
                self.run_kit()
            self.assertEqual(requests, [])
            self.assertFalse((self.directory / "attempt.private.json").exists())

    def test_stale_future_wrong_challenge_and_source_fail_before_inference(self):
        with engine(echo) as (url, requests):
            original = self.package(self.prepare(url))
            changes = [{"observed_at": time.time() - 901}, {"observed_at": time.time() + 120},
                       {"challenge_sha256": "0" * 64}, {"source_sha256": "0" * 64}, {"role": "controller"}]
            for change in changes:
                write_json(self.engine_path, {**original, **change})
                with self.subTest(change=change), self.assertRaises(ValueError):
                    self.run_kit()
            self.assertEqual(requests, [])

    def test_unknown_identity_or_unobserved_gpu_does_not_become_two_host_proof(self):
        record = self.package(self.prepare())
        challenge = kit.challenge_at(self.directory / "challenge.json")
        with patch.object(kit, "host_identity", return_value=None), self.assertRaises(ValueError):
            kit.collect(challenge, "controller", self.root)
        for changes in ({"gpu_probe": "unavailable"}, {"devices": []}):
            write_json(self.engine_path, {**record, **changes})
            with self.assertRaises(ValueError):
                self.run_kit()

    def test_one_request_public_export_is_offline_and_does_not_leak_private_fields(self):
        with engine(echo) as (url, requests), patch.dict(os.environ, {"KIT_TEST_TOKEN": "synthetic-private-token"}):
            config = self.prepare(url); config["profiles"][0]["api_key_env"] = "KIT_TEST_TOKEN"
            config["project_id"] = "private-project"
            record = self.package(config)
            record["extra_private_note"] = "PRIVATE-NOTE"; write_json(self.engine_path, record)
            result = self.run_kit()
            self.assertTrue(result["smoke_completed"])
            self.assertEqual(len(requests), 1)
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
                public = kit.export(self.directory)
            text = json.dumps(public)
            for private in (url, "KIT_TEST_TOKEN", "synthetic-private-token", "private-project", "test-target", "PRIVATE-NOTE"):
                self.assertNotIn(private, text)
            self.assertTrue(public["claims"]["distinct_os_installations_recorded"])
            self.assertTrue(public["claims"]["response_predicate_checked"])
            for claim in ("gpu_execution_verified", "endpoint_host_binding_verified", "speedup_measured", "production_ready"):
                self.assertFalse(public["claims"][claim])
            self.assertEqual(public["observations"]["engine_gpu_count"], 2)
            self.assertEqual(public["observations"]["selected_vram_mib"], 12288)

    def test_existing_attempt_cannot_reexecute_even_if_first_model_check_failed(self):
        with engine() as (url, requests):
            self.package(self.prepare(url))
            self.assertFalse(self.run_kit()["smoke_completed"])
            with self.assertRaises(ValueError):
                self.run_kit()
            self.assertEqual(len(requests), 1)
            with self.assertRaises(ValueError):
                kit.export(self.directory)

    def test_altered_config_and_task_are_refused_before_network(self):
        self.package(self.prepare())
        task = load(self.directory / "task.json"); task["prompt"] = "changed"
        write_json(self.directory / "task.json", task)
        with self.assertRaises(ValueError):
            self.run_kit()
        config = load(self.directory / "config.private.json"); config["budgets"]["max_output_tokens"] += 1
        write_json(self.directory / "config.private.json", config)
        with self.assertRaises(ValueError):
            self.run_kit()

    def test_changed_source_refuses_old_evidence(self):
        self.package(self.prepare())
        with patch.object(kit, "source_digest", return_value="0" * 64), self.assertRaises(ValueError):
            kit.challenge_at(self.directory / "challenge.json")

    def test_export_rechecks_saved_output_and_measurement_types(self):
        with engine(echo) as (url, _):
            self.package(self.prepare(url)); self.run_kit()
        output_path = self.directory / "run/output.private.json"
        output = load(output_path); output[0]["text"] = "wrong"
        write_json(output_path, output)
        with self.assertRaises(ValueError):
            kit.export(self.directory)
        output[0]["text"] = kit.smoke_task(kit.challenge_at(self.directory / "challenge.json"))["expected"]
        write_json(output_path, output)
        report_path = self.directory / "run/report.json"
        report = load(report_path); report["observations"][0]["response_chain_ms"] = True
        write_json(report_path, report)
        with self.assertRaises(ValueError):
            kit.export(self.directory)

    def test_missing_memory_receipt_stays_unknown_and_foreign_receipt_is_refused(self):
        with engine(echo) as (url, _):
            self.package(self.prepare(url)); self.run_kit()
        self.assertFalse(kit.export(self.directory)["observations"]["memory_receipt_recorded"])
        write_json(self.directory / "run/memory-receipt.json", {"project_id": "another-project", "quarantined": True})
        with self.assertRaises(ValueError):
            kit.export(self.directory)

    def test_export_uses_probe_freshness_at_run_time_not_at_later_review(self):
        with engine(echo) as (url, _):
            self.package(self.prepare(url)); self.run_kit()
        with patch.object(kit.time, "time", return_value=time.time() + 86400):
            self.assertTrue(kit.export(self.directory)["claims"]["response_predicate_checked"])

    def test_cli_dispatch_and_no_overwrite(self):
        from skills.llm_backends.runtime_cli import main
        result = subprocess.run([sys.executable, "-m", "skills.cli", "runtime", "acceptance", "--help"],
                                text=True, encoding="utf-8", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("collect", result.stdout)
        config_path = self.root / "config.json"; write_json(config_path, self.prepare())
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            args = ["acceptance", "prepare", str(config_path), "--directory", str(self.directory)]
            self.assertEqual(main(args), 0)
            self.assertEqual(main(args), 2)

    def test_real_memory_receipt_and_capture_only_retry(self):
        from skills.memory_hub.cli import initialize
        from skills.memory_hub.shared_http import AuthRegistry, MemoryHTTPServer, read_token
        from skills.memory_hub.shared_service import MemoryService
        from skills.llm_backends.runtime import capture
        memory = self.root / "memory"; initialize(memory, "my-project")
        server = MemoryHTTPServer(("127.0.0.1", 0), MemoryService(memory / "data"), AuthRegistry.load(memory / "auth.json"))
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        try:
            with engine(echo) as (url, requests), patch.dict(os.environ, {"BOTTE_MEMORY_TOKEN": read_token(memory / "worker.secret")}):
                config = self.prepare(url, memory="botte_http")
                config["memory"]["url"] = f"http://127.0.0.1:{server.server_port}"
                self.package(config); self.run_kit(record_memory=True)
                self.assertTrue(kit.export(self.directory)["observations"]["memory_receipt_recorded"])
                original = load(self.directory / "run/config.private.json")
                self.assertTrue(capture(original, self.directory / "run")["replayed"])
                self.assertEqual(len(requests), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
