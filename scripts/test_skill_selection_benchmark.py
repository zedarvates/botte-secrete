"""Acceptance-runner regressions with injected transport, never real inference."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_skill_selection as bench


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = bench.load_corpus(bench.ROOT / "docs/examples/skill-selection-cases.json")
        self.small = {**self.corpus, "cases": self.corpus["cases"][:1]}
        self.args = SimpleNamespace(baseline=bench.ROOT, candidate=bench.ROOT, repetitions=1,
                                    timeout=2, execute=False, model="fixture-model", runtime_id="fixture")
        self.spec = bench.make_spec(self.args, self.small)
        self.calls = []

    def fake_process(self, command, **kwargs):
        job = json.loads(kwargs["input"])
        self.calls.append(job)
        result = {"job_sha256": bench.digest(job), "paths": self.small["cases"][0]["expected_paths"],
                  "shortlist": list(self.corpus["skills"]), "review_status": "selected",
                  "review_reason": None, "tier": "local-llm-reranked",
                  "measurements": {"calls": 1, "latency_ms": 12.5, "prompt_tokens": 100,
                                   "completion_tokens": 2, "response_model_matches": True,
                                   "truncated": False, "prompt_bytes": 400}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(result))

    def execute(self, **kwargs):
        with patch.object(bench.subprocess, "run", side_effect=self.fake_process):
            return bench.run(self.spec, self.small, self.root / "run", **kwargs)

    def test_starter_covers_positive_and_negative_operations(self):
        self.assertEqual(len(self.corpus["cases"]), 12)
        self.assertEqual(sum(not c["expected_paths"] for c in self.corpus["cases"]), 6)
        self.assertEqual(self.corpus["dataset_class"], "fixture")
        for job in self.spec["jobs"].values():
            self.assertNotIn("expected_paths", job)
            self.assertNotIn("rationale", job)

    def test_invalid_oracle_and_path_are_rejected_before_execution(self):
        for mutate in (
            lambda d: d["skills"].update({"../escape/SKILL.md": "body"}),
            lambda d: d["cases"][0].update(expected_paths=["unknown/SKILL.md"]),
            lambda d: d["cases"].append(d["cases"][0]),
            lambda d: d["cases"].__setitem__(0, []),
            lambda d: d["cases"][0].update(expected_paths=[[]]),
            lambda d: d.update(dataset_class="reviewed_holdout", review_evidence=[]),
        ):
            data = json.loads(json.dumps(self.corpus))
            mutate(data)
            path = self.root / "invalid.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                bench.load_corpus(path)
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            bench.load_corpus(path)

    def test_cli_preview_is_offline_and_writes_nothing(self):
        output = self.root / "preview"
        proc = subprocess.run([sys.executable, str(Path(bench.__file__)), "--baseline", str(bench.ROOT),
                               "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "prepared")
        self.assertEqual(report["planned_calls"], 24)
        self.assertEqual(report["inference_calls"], 0)
        self.assertIsNone(report["local_cost"])
        self.assertFalse(output.exists())

    def test_completed_observations_are_reused_without_inference(self):
        before = self.execute()
        self.assertEqual(len(self.calls), 2)
        after = self.execute(resume=True)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(before, after)
        self.assertEqual(after["status"], "measurement_complete")
        self.assertEqual(after["decision"], "collect_held_out_evidence")
        self.assertFalse(after["automatic_promotion"])

    def test_interruption_remains_uncertain_and_is_never_replayed(self):
        first = next(iter(self.spec["jobs"]))
        with patch.object(bench.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 1)):
            before = bench.run(self.spec, self.small, self.root / "run")
        after = self.execute(resume=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(after["status"], "insufficient_evidence")
        self.assertEqual(before["totals"]["baseline"]["observed"], 0)
        checkpoint = json.loads((self.root / "run/checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["results"][0]["id"], first)
        self.assertEqual(checkpoint["results"][0]["status"], "uncertain")

    def test_mutated_observation_is_not_consumed_or_replayed(self):
        self.execute()
        path = next((self.root / "run/results").glob("*.json"))
        result = json.loads(path.read_text(encoding="utf-8"))
        result["measurements"]["prompt_tokens"] = 1
        path.write_text(json.dumps(result), encoding="utf-8")
        after = self.execute(resume=True)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(after["status"], "insufficient_evidence")
        self.assertEqual(len(after["observations"]), 1)

    def test_resume_runs_only_the_remaining_unstarted_jobs(self):
        self.small = {**self.corpus, "cases": self.corpus["cases"][:2]}
        self.spec = bench.make_spec(self.args, self.small)
        attempted = []
        def interrupted(*args, **kwargs):
            attempted.append(json.loads(kwargs["input"])["case_id"])
            if len(attempted) == 2:
                raise KeyboardInterrupt()
            return self.fake_process(*args, **kwargs)
        with patch.object(bench.subprocess, "run", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                bench.run(self.spec, self.small, self.root / "run")
        report = self.execute(resume=True)
        self.assertEqual(len(self.calls), 3)  # first success plus two previously unstarted jobs
        self.assertEqual(report["attempts_started"], 4)
        self.assertEqual(report["status"], "insufficient_evidence")
        self.assertIsNone(report["totals"]["candidate"]["prompt_tokens"])

    def test_changed_runtime_or_source_rejects_resume(self):
        self.execute()
        original = (self.root / "run/checkpoint.json").read_bytes()
        for key in ("runtime_sha256", "sources"):
            changed = {**self.spec, key: "changed"}
            with self.assertRaises(ValueError):
                bench.run(changed, self.small, self.root / "run", resume=True)
        self.assertEqual((self.root / "run/checkpoint.json").read_bytes(), original)

    def test_unknown_tokens_stay_unknown(self):
        original = self.fake_process
        def without_usage(*args, **kwargs):
            proc = original(*args, **kwargs)
            data = json.loads(proc.stdout)
            data["measurements"]["prompt_tokens"] = None
            proc.stdout = json.dumps(data)
            return proc
        with patch.object(bench.subprocess, "run", side_effect=without_usage):
            report = bench.run(self.spec, self.small, self.root / "run")
        self.assertEqual(report["status"], "insufficient_evidence")
        self.assertIsNone(report["totals"]["candidate"]["prompt_tokens"])
        self.assertIsNone(report["monetary_cost"])

    def test_full_client_prompt_and_missing_usage(self):
        from skills.llm_backends.client import LocalLLMClient
        job = next(iter(self.spec["jobs"].values())).copy()
        job["skills"] = {"a/memory/SKILL.md": "---\nname: memory\n---\nInspect notes. Exclude deletion.",
                         "b/memory/SKILL.md": "---\nname: memory\n---\nInspect notes. Require a project."}
        job["task"] = "inspect notes"
        job["backend"] = dict(kind="fixture", label="fixture", host="127.0.0.1", port=1,
                              api="openai", chat=True, models=["fixture-model"], base_url="http://127.0.0.1:1")
        payload = {"model": "fixture-model", "choices": [{"message": {"content": "2"}, "finish_reason": "stop"}]}
        with patch.object(LocalLLMClient, "_post", return_value=payload) as transport:
            result = bench.worker(job)
        sent = transport.call_args.args[1]
        self.assertEqual(sent["model"], "fixture-model")
        for body in job["skills"].values():
            self.assertIn(json.dumps(body), sent["messages"][0]["content"])
        self.assertEqual(result["paths"], ["b/memory/SKILL.md"])
        self.assertIsNone(result["measurements"]["prompt_tokens"])
        self.assertEqual(result["measurements"]["calls"], 1)

    def test_truncated_or_different_model_cannot_pass_selection(self):
        original = self.fake_process
        for field, value in (("truncated", True), ("response_model_matches", False)):
            def invalid(*args, **kwargs):
                proc = original(*args, **kwargs)
                data = json.loads(proc.stdout)
                data["measurements"][field] = value
                proc.stdout = json.dumps(data)
                return proc
            with patch.object(bench.subprocess, "run", side_effect=invalid):
                report = bench.run(self.spec, self.small, self.root / field)
            self.assertEqual(report["status"], "insufficient_evidence")
            self.assertEqual(report["totals"]["candidate"]["exact_selections"], 0)

    def test_malformed_observation_cannot_satisfy_pipeline(self):
        original = self.fake_process
        def malformed(*args, **kwargs):
            proc = original(*args, **kwargs)
            data = json.loads(proc.stdout)
            data["measurements"]["prompt_tokens"] = True
            proc.stdout = json.dumps(data)
            return proc
        with patch.object(bench.subprocess, "run", side_effect=malformed):
            report = bench.run(self.spec, self.small, self.root / "run")
        self.assertEqual(report["status"], "insufficient_evidence")
        self.assertEqual(report["observations"], [])
        self.assertEqual(report["attempts_started"], 2)

    def test_fresh_processes_use_one_explicit_http_fixture_and_resume(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(request)
                payload = {"model": request["model"], "usage": {"prompt_tokens": 101, "completion_tokens": 1},
                           "choices": [{"message": {"content": "1"}, "finish_reason": "stop"}]}
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            backend = dict(kind="fixture", label="test-only", host="127.0.0.1", port=port,
                           api="openai", chat=True, models=["fixture-model"], base_url=f"http://127.0.0.1:{port}")
            registry = self.root / "registry.json"
            registry.write_text(json.dumps({"backends": [backend]}), encoding="utf-8")
            self.args.execute, self.args.registry, self.args.backend = True, registry, "test-only"
            spec = bench.make_spec(self.args, self.small)
            report = bench.run(spec, self.small, self.root / "http-run")
            self.assertEqual(report["status"], "measurement_complete", report["gaps"])
            self.assertEqual(len(requests), 2)
            self.assertEqual(report["totals"]["candidate"]["prompt_tokens"], 101)
            resumed = bench.run(spec, self.small, self.root / "http-run", resume=True)
            self.assertEqual(report, resumed)
            self.assertEqual(len(requests), 2)
            for request in requests:
                self.assertEqual(request["model"], "fixture-model")
                self.assertEqual(request["temperature"], 0.0)
                self.assertNotIn("expected_paths", request["messages"][0]["content"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(AcceptanceTests))
    failed = len(result.errors) + len(result.failures)
    print(f"RESULT: {max(0, result.testsRun - failed)} passed, {failed} failed, 0 skipped")
    raise SystemExit(0 if result.wasSuccessful() else 1)
