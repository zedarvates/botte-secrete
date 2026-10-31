"""Isolated loopback evidence: no live models, agents, subnet or credentials."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from skills.capabilities.observations import (
    ObservationSession, digest, empty_report, observed_operation,
    submit_observed, summarize, validate_report,
)
from skills.conductor.observed_run import read_checkpoint
from skills.llm_backends.client import LocalLLMClient, LocalLLMError
from skills.llm_backends.discovery import Backend, Probe

REPO = Path(__file__).resolve().parents[2]
PRIVATE = "fixture-PRIVATE-prompt-and-token-82467"


class NetworkObservationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        proxy = patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
        proxy.start()
        self.addCleanup(proxy.stop)
        self.mode = "chat"
        self.requests = []
        self.redirect = ""
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.answer()

            def do_POST(self):
                self.answer()

            def answer(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                case.requests.append((self.command, self.path, raw, self.headers.get("X-Botte-Token")))
                if case.mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", case.redirect)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                code = 202 if case.mode == "accepted" else 503 if case.mode == "http_error" else 200
                text = 'not an object' if case.mode == "retry" and len(case.requests) == 1 else '{"ok":true}'
                body = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                                   "data": [{"id": "fixture-model"}], "accepted": True,
                                   "completed": False, "ok": False}).encode("utf-8")
                if case.mode == "malformed":
                    body = PRIVATE.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if case.mode == "read_timeout":
                    threading.Event().wait(0.8)
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        backend = Backend("fixture", "fixture", "127.0.0.1", self.port, "openai", True,
                          ["fixture-model"], 0, self.url)
        self.client = LocalLLMClient(backend, timeout=2)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def assert_private(self, report):
        encoded = json.dumps(report)
        self.assertNotIn(PRIVATE, encoded)
        self.assertNotIn(self.url, encoded)
        self.assertNotIn('"headers"', encoded)
        self.assertEqual(validate_report(report), [])

    def test_parallel_discovery_links_tcp_and_http_to_each_probe(self):
        from skills.llm_backends import discovery
        probes = tuple(Probe(f"fixture{i}", "fixture", self.port, "/v1/models", "openai", True)
                       for i in range(4))
        from skills.atomic_json import write_json
        def checked_write(path, data, **kwargs):
            self.assertEqual(validate_report(data), [])  # Includes in-flight response checkpoints.
            return write_json(path, data, **kwargs)
        checkpoint = self.root / "evidence.json"
        with patch.object(discovery, "PROBES", probes), patch("skills.atomic_json.write_json", checked_write):
            with ObservationSession(checkpoint=checkpoint) as session:
                found = discovery.discover(["127.0.0.1"], max_workers=4, timeout=3)
        report = session.report
        self.assertEqual(len(found), 4)
        self.assertEqual(len(report["network"]), 8)
        self.assertEqual(len({n["id"] for n in report["network"]}), 8)
        parent = report["calls"][0]
        self.assertEqual(parent["operation"], "discover")
        for call in report["calls"][1:]:
            self.assertEqual(call["parent_id"], parent["id"])
            attempts = [n for n in report["network"] if n["call_id"] == call["id"]]
            self.assertEqual([n["transport"] for n in attempts], ["tcp", "http"])
        self.assertEqual(summarize(report)["http_responses"], 4)
        self.assertTrue(all(n["comparison"] == "supported" for n in report["network"]))
        self.assertEqual(read_checkpoint(checkpoint, report["run_id"]), report)
        self.assert_private(report)

    def test_chat_retry_records_two_transfers_without_storing_prompt_or_response(self):
        self.mode = "retry"
        with ObservationSession() as session:
            answer = self.client.chat_json(PRIVATE, retries=1)
        self.assertEqual(answer, {"ok": True})
        self.assertEqual(len(self.requests), 2)
        self.assertIn(PRIVATE.encode(), self.requests[0][2])  # The real fixture received the payload.
        self.assertEqual([c["operation"] for c in session.report["calls"]], ["chat_json", "chat", "chat"])
        self.assertEqual(len(session.report["network"]), 2)
        self.assertTrue(all(n["remote_effects"] == "unknown" for n in session.report["network"]))
        self.assert_private(session.report)

    def test_http_acceptance_is_not_remote_task_completion(self):
        from skills.cluster.cluster import delegate
        self.mode = "accepted"
        with ObservationSession() as session:
            result = delegate("127.0.0.1", PRIVATE, token=PRIVATE, agent_url=self.url + "/task")
        self.assertTrue(result["delegated"])
        self.assertFalse(json.loads(result["response"])["completed"])
        observation = session.report["network"][0]
        self.assertEqual(observation["http_status"], 202)
        self.assertEqual(observation["remote_effects"], "unknown")
        self.assertEqual(observation["comparison"], "supported")
        self.assertEqual(self.requests[0][3], PRIVATE)
        self.assert_private(session.report)

    def test_rejected_endpoint_produces_no_network_evidence(self):
        from skills.cluster.cluster import delegate
        with ObservationSession() as session:
            result = delegate("agent.invalid", PRIVATE, agent_url=self.url + "/task", token=PRIVATE)
        self.assertFalse(result["delegated"])
        self.assertEqual(self.requests, [])
        self.assertEqual(session.report["network"], [])

    def test_delegation_never_follows_redirect_with_task_or_token(self):
        from skills.cluster.cluster import delegate
        received = []
        class Receiver(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                received.append(self.headers.get("X-Botte-Token"))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            do_POST = do_GET
        other = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        thread = threading.Thread(target=other.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            self.mode = "redirect"
            self.redirect = f"http://127.0.0.1:{other.server_address[1]}/task"
            # The endpoint boundary holds even without observation enabled.
            result = delegate("127.0.0.1", PRIVATE, token=PRIVATE, agent_url=self.url + "/task")
            self.assertFalse(result["delegated"])
            with ObservationSession() as session:
                result = delegate("127.0.0.1", PRIVATE, token=PRIVATE, agent_url=self.url + "/task")
            self.assertFalse(result["delegated"])
            self.assertEqual(received, [])
            record = session.report["network"][0]
            self.assertEqual(record["http_status"], 302)
            self.assertEqual(record["error_kind"], "http_error")
            self.assertEqual(summarize(session.report)["next_action"], "inspect_partial_state_before_retry")
            self.assert_private(session.report)
            # Existing discovery GET redirects are observed, not silently
            # attributed to the original origin or granted delegation scope.
            from skills.llm_backends.discovery import probe_host
            probe = Probe("fixture", "fixture", self.port, "/v1/models", "openai", True)
            with ObservationSession() as redirected:
                probe_host("127.0.0.1", probe)
            http = redirected.report["network"][-1]
            self.assertTrue(http["origin_changed"])
            self.assertNotEqual(http["target"]["id"], http["response_target"]["id"])
            self.assertEqual(received, [None])
            self.assert_private(redirected.report)
        finally:
            other.shutdown()
            other.server_close()
            thread.join(timeout=2)

    def test_read_timeout_retains_headers_without_claiming_complete_response(self):
        self.mode = "read_timeout"
        self.client.timeout = 0.2
        with ObservationSession() as session:
            with self.assertRaises(LocalLLMError):
                self.client.chat(PRIVATE)
        record = session.report["network"][0]
        self.assertEqual(record["http_status"], 200)
        self.assertEqual(record["status"], "raised")
        self.assertEqual(record["error_kind"], "timeout")
        self.assertFalse(record["response_complete"])
        self.assertEqual(record["remote_effects"], "unknown")
        self.assert_private(session.report)

    def test_http_error_and_malformed_application_response_remain_distinct(self):
        for mode in ("http_error", "malformed"):
            self.mode = mode
            with ObservationSession() as session:
                with self.assertRaises((LocalLLMError, ValueError)):
                    self.client.chat(PRIVATE)
            record = session.report["network"][0]
            self.assertEqual(record["http_status"], 503 if mode == "http_error" else 200)
            self.assertEqual(record["status"], "raised" if mode == "http_error" else "returned")
            self.assertEqual(record["remote_effects"], "unknown")
            self.assertEqual(session.report["calls"][0]["status"], "raised")
            self.assert_private(session.report)

    def test_tcp_refusal_is_visible_even_when_probe_returns_none(self):
        from skills.llm_backends import discovery
        probe = Probe("fixture", "fixture", self.port, "/v1/models", "openai", True)
        with patch.object(discovery.socket, "create_connection", side_effect=ConnectionRefusedError(PRIVATE)):
            with ObservationSession() as session:
                result = discovery.probe_host("127.0.0.1", probe)
        self.assertIsNone(result)
        self.assertEqual(len(session.report["network"]), 1)
        self.assertEqual(session.report["network"][0]["error_kind"], "network_error")
        self.assertEqual(session.report["calls"][0]["status"], "returned")
        self.assert_private(session.report)

    def test_observation_limit_does_not_cancel_network_work(self):
        with patch("skills.capabilities.network_observations._http_target", side_effect=AssertionError):
            self.client.chat(PRIVATE)  # Inactive observation must not inspect network metadata.
        with patch("skills.capabilities.network_observations.MAX_NETWORK", 1):
            with ObservationSession() as session:
                self.client.chat(PRIVATE)
                self.client.chat(PRIVATE)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(len(session.report["network"]), 1)
        self.assertTrue(session.report["problems"])
        self.assert_private(session.report)

    def test_late_worker_cannot_rewrite_a_closed_session(self):
        started, release = threading.Event(), threading.Event()
        @observed_operation("background_fixture")
        def worker():
            started.set()
            release.wait(2)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with ObservationSession() as session:
                future = submit_observed(pool, worker)
                self.assertTrue(started.wait(2))
            frozen = deepcopy(session.report)
            release.set()
            future.result(timeout=2)
        self.assertEqual(session.report, frozen)
        self.assertEqual(session.report["calls"][0]["status"], "running")
        self.assertTrue(session.report["problems"])
        self.assertEqual(validate_report(session.report), [])

    def test_stale_or_missing_declarations_do_not_validate_transport_facets(self):
        from skills.capabilities.effects import inspect_effects
        snapshot = inspect_effects(REPO / "skills" / "llm_backends")
        for unavailable in ({**snapshot, "status": "stale"}, {"status": "missing", "errors": []}):
            with patch("skills.capabilities.observations.inspect_effects", return_value=unavailable):
                with ObservationSession() as session:
                    self.client.chat(PRIVATE)
            self.assertEqual(session.report["network"][0]["http_status"], 200)
            self.assertEqual(session.report["network"][0]["comparison"], "unknown")
            self.assertEqual(validate_report(session.report), [])

    def test_v1_reader_and_invalid_v2_evidence(self):
        old = empty_report()
        old["schema"] = "botte.effect-observations/v1"
        del old["network"]
        self.assertEqual(validate_report(old), [])
        path = self.root / "legacy.json"
        path.write_text(json.dumps(old), encoding="utf-8")
        self.assertEqual(read_checkpoint(path, old["run_id"]), old)
        with ObservationSession() as session:
            self.client.chat(PRIVATE)
        for field, value in (("remote_effects", "verified"), ("http_status", 600),
                             ("comparison", "unknown"), ("call_id", "absent"),
                             ("effect_ref", "/expected_effects/999"), ("origin_changed", True),
                             ("headers", {"Authorization": PRIVATE})):
            report = deepcopy(session.report)
            report["network"][0][field] = value
            self.assertTrue(validate_report(report), field)
        report = deepcopy(session.report)
        report["network"][0]["response_target"] = {
            "id": "t99", "scheme": "tcp", "address_kind": "loopback"}
        report["network"][0]["origin_changed"] = True
        self.assertTrue(validate_report(report))  # HTTP cannot return a TCP URL origin.
        report = deepcopy(session.report)
        ref, declaration = next(iter(report["declarations"].items()))
        del declaration["capability_id"]
        report["declarations"] = {digest(declaration): declaration}
        self.assertTrue(validate_report(report))  # Malformed metadata must not raise KeyError.


def main() -> int:
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(NetworkObservationTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
