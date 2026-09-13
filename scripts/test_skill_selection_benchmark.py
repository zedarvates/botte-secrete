"""Acceptance-runner regressions with injected transport, never real inference."""

from __future__ import annotations

import copy
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
        self.assertEqual(after["decision"], "collect_representative_cases")
        self.assertEqual(after["acceptance"]["coverage_gaps"], ["no_negative_cases"])
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

    def test_quality_refusal_is_retained_on_resume_without_new_calls(self):
        self.small = {**self.corpus, "cases": [self.corpus["cases"][0], self.corpus["cases"][6]]}
        self.spec = bench.make_spec(self.args, self.small)
        before = self.execute()
        self.assertEqual(before["status"], "measurement_complete")
        self.assertEqual(before["decision"], "do_not_promote")
        self.assertEqual(bench.exit_code(before), 4)
        self.assertEqual(self.execute(resume=True), before)
        self.assertEqual(len(self.calls), 4)

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


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.corpus = bench.load_corpus(bench.ROOT / "docs/examples/skill-selection-cases.json")
        self.path = bench.ROOT / "docs/validation/skill-selection-cpu-v1.json"
        self.report = json.loads(self.path.read_text(encoding="utf-8"))

    def perfect(self):
        report = copy.deepcopy(self.report)
        cases = {c["id"]: c["expected_paths"] for c in self.corpus["cases"]}
        for row in report["observations"]:
            row["paths"] = list(cases[row["case_id"]])
            row["review_status"] = "selected" if row["paths"] else "abstained"
            row["tier"] = "local-llm-reranked"
        return report

    def test_real_failures_are_reassessed_without_inference_or_mutation(self):
        before = self.path.read_bytes()
        with patch.object(bench.subprocess, "run", side_effect=AssertionError("no execution")):
            result = bench.assess_file(self.path, bench.file_hash(self.path), self.corpus)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(result["inference_calls"], 0)
        self.assertEqual(bench.exit_code(result), 4)
        assessment = result["acceptance"]
        self.assertEqual(assessment["state"], "not_accepted")
        self.assertEqual(len(assessment["candidate_excluded_selections"]), 6)
        self.assertEqual(len(assessment["candidate_failures"]), 7)
        self.assertEqual(assessment["totals"]["baseline"]["exact"], 2)
        self.assertEqual(assessment["totals"]["candidate"]["exact"], 5)
        self.assertEqual(assessment["lost_reviewed_selections"], [])
        self.assertEqual(assessment["lost_required_paths"], [{
            "job": "r0-two-destinations-candidate", "paths": ["team/memory/SKILL.md"]}])

    def test_stored_scores_cannot_override_observed_paths(self):
        original = bench.assess_selection(self.report, self.corpus)
        self.report["totals"]["candidate"]["exact_selections"] = 12
        for row in self.report["observations"]:
            row["exact_selection"] = True
            row["false_selections"] = 0
        self.assertEqual(bench.assess_selection(self.report, self.corpus), original)

    def test_perfect_fixture_and_reviewed_corpus_never_promote(self):
        for kind, state in (("fixture", "fixture_only"), ("reviewed_holdout", "review_required")):
            corpus = {**self.corpus, "dataset_class": kind, "review_evidence": ["test-only-review-reference"]}
            report = self.perfect()
            report.update(dataset_class=kind, corpus_sha256=bench.digest(corpus))
            assessment = bench.assess_selection(report, corpus)
            self.assertEqual(assessment["state"], state)
            self.assertFalse(assessment["automatic_promotion"])
            self.assertEqual(assessment["operation_quality"], "unmeasured")

    def test_new_exclusion_and_lost_reviewed_selection_are_named(self):
        report = self.perfect()
        for row in report["observations"]:
            if row["side"] == "candidate" and row["case_id"] in {"wrong-owner", "private-note"}:
                row["paths"] = ["team/memory/SKILL.md"]
                row["review_status"] = "selected"
        assessment = bench.assess_selection(report, self.corpus)
        self.assertEqual(assessment["new_excluded_selections"], ["r0-wrong-owner-candidate"])
        self.assertEqual(assessment["lost_reviewed_selections"], ["r0-private-note-candidate", "r0-wrong-owner-candidate"])
        self.assertEqual(assessment["state"], "not_accepted")

    def test_missing_or_uncomparable_observation_requires_reconciliation(self):
        for mutate in (
            lambda r: r["observations"].pop(),
            lambda r: r["observations"][0]["measurements"].update(prompt_tokens=None),
            lambda r: r["observations"][0]["measurements"].update(response_model_matches=False),
            lambda r: r["observations"][0]["measurements"].update(truncated=True),
            lambda r: r["gaps"].append({"job": "fixture", "reason": "unresolved"}),
        ):
            report = self.perfect()
            mutate(report)
            assessment = bench.assess_selection(report, self.corpus)
            self.assertEqual(assessment["state"], "insufficient_evidence")
            self.assertEqual(assessment["decision"], "reconcile_run")
            self.assertEqual(bench.exit_code({"status": "assessed", "acceptance": assessment}), 3)

    def test_duplicate_mispaired_or_invalid_rows_are_rejected(self):
        for mutate in (
            lambda r: r["observations"].__setitem__(1, r["observations"][0]),
            lambda r: r["observations"][0].update(side="candidate"),
            lambda r: r["observations"][0].update(repeat=True),
            lambda r: r["observations"][0].update(shortlist=[]),
            lambda r: r["observations"][0]["measurements"].update(prompt_tokens=True),
            lambda r: r["observations"][0]["measurements"].update(latency_ms=float("nan")),
            lambda r: r.update(planned_calls=23),
            lambda r: r.update(attempts_started=23),
        ):
            report = self.perfect()
            mutate(report)
            with self.assertRaises(ValueError):
                bench.assess_selection(report, self.corpus)

    def test_unavailable_or_inconsistent_abstention_cannot_pass(self):
        report = self.perfect()
        row = next(r for r in report["observations"] if r["job"] == "r0-wrong-owner-candidate")
        row.update(review_status="unavailable", tier="free-lexical")
        assessment = bench.assess_selection(report, self.corpus)
        self.assertIn(row["job"], assessment["candidate_failures"])
        self.assertEqual(assessment["state"], "not_accepted")
        row.update(review_status="abstained", tier="local-llm-reranked", paths=["personal/memory/SKILL.md"])
        with self.assertRaises(ValueError):
            bench.assess_selection(report, self.corpus)

    def test_one_bad_repetition_is_not_averaged_away(self):
        report = self.perfect()
        repeated = copy.deepcopy(report["observations"])
        for row in repeated:
            row["repeat"] = 1
            row["job"] = row["job"].replace("r0-", "r1-", 1)
            if row["job"] == "r1-wrong-owner-candidate":
                row.update(paths=["personal/memory/SKILL.md"], review_status="selected")
        report["observations"].extend(repeated)
        report.update(planned_calls=48, attempts_started=48)
        assessment = bench.assess_selection(report, self.corpus)
        self.assertEqual(assessment["candidate_excluded_selections"], ["r1-wrong-owner-candidate"])
        self.assertEqual(assessment["repetitions"], 2)
        self.assertEqual(assessment["state"], "not_accepted")

    def test_changed_report_hash_or_corpus_rejects_offline_assessment(self):
        with self.assertRaises(ValueError):
            bench.assess_file(self.path, "0" * 64, self.corpus)
        changed = copy.deepcopy(self.corpus)
        changed["cases"][0]["expected_paths"] = []
        with self.assertRaises(ValueError):
            bench.assess_file(self.path, bench.file_hash(self.path), changed)

    def test_offline_cli_returns_quality_refusal_and_rejects_execution_flags(self):
        command = [sys.executable, str(Path(bench.__file__)), "--assess", str(self.path),
                   "--report-sha256", bench.file_hash(self.path)]
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 4, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["acceptance"]["decision"], "do_not_promote")
        for extra in (["--execute"], ["--resume"], ["--repetitions", "2"], ["--timeout", "1"],
                      ["--output", "unused-output"], ["--backend", "unused-backend"]):
            proc = subprocess.run(command + extra, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["status"], "blocked")


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    failed = len(result.errors) + len(result.failures)
    print(f"RESULT: {max(0, result.testsRun - failed)} passed, {failed} failed, 0 skipped")
    raise SystemExit(0 if result.wasSuccessful() else 1)
