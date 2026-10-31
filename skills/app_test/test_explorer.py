"""Interface exploration contracts and a real loopback HTML navigation test.

The HTTP fixture is a live local software interface. No browser rendering,
desktop control, visual matching or real-time game execution is qualified.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from skills.app_test.explorer import (
    DeclarativeAdapter, LoopbackHttpAdapter, explore_interface,
)


MODEL = {"scope": "test-app", "initial_state": "home", "states": {
    "home": {"actions": {"open": "form", "broken": None, "external": "outside"}},
    "form": {"actions": {"submit": "done", "back": "home"}},
    "done": {"actions": {}, "terminal": True},
    "outside": {"actions": {}},
    "secret": {"actions": {}, "terminal": True},
}}


class ExplorerTests(unittest.TestCase):
    def explore(self, **kwargs):
        defaults = {"scope": "test-app", "allowed_actions": ["open", "submit", "back"]}
        defaults.update(kwargs)
        return explore_interface(DeclarativeAdapter(MODEL), **defaults)

    def test_model_graph_traverses_cycles_and_preserves_scope_limits(self):
        report = self.explore(goals=["done", "secret"])
        self.assertEqual(report["status"], "completed")
        self.assertEqual({row["state_id"] for row in report["states"]}, {"home", "form", "done"})
        self.assertEqual(report["coverage"]["goals_observed"], ["done"])
        self.assertEqual(report["coverage"]["goals_not_observed"], ["secret"])
        self.assertEqual(report["coverage"]["global"], "unknown")
        self.assertTrue(report["coverage"]["allowed_frontier_exhausted"])
        self.assertEqual(report["coverage"]["excluded_actions"], 2)
        self.assertFalse(report["boundaries"]["graphical_qualification"])
        self.assertEqual(report["adapter_kind"], "model_replay")
        self.assertGreater(report["budget"]["replay_actions"], 0)
        self.assertEqual(len(report["provenance"]["graph_sha256"]), 64)
        self.assertEqual(self.explore()["provenance"], report["provenance"])

    def test_failed_transition_is_a_failure_not_a_discovered_destination(self):
        report = self.explore(allowed_actions=["broken"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["transitions"], [{"source": "home", "action": "broken",
                                                  "status": "failed", "reason": "declared_transition_failure"}])
        self.assertTrue(report["coverage"]["allowed_frontier_exhausted"])

    def test_dead_end_is_distinguished_from_terminal_state(self):
        report = self.explore(allowed_actions=["external"])
        self.assertEqual(report["dead_ends"], ["outside"])
        self.assertNotIn("done", self.explore()["dead_ends"])

    def test_replays_share_action_budget_and_goal_does_not_imply_coverage(self):
        report = self.explore(max_actions=3, goals=["done"])
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["coverage"]["goals_observed"], ["done"])
        self.assertFalse(report["coverage"]["allowed_frontier_exhausted"])
        self.assertEqual(report["budget"]["actions"], 3)
        self.assertEqual(report["budget"]["stop_reason"], "action_budget")

    def test_zero_action_budget_never_performs_an_action(self):
        report = self.explore(max_actions=0)
        self.assertEqual(report["transitions"], [])
        self.assertEqual(report["budget"]["actions"], 0)
        self.assertEqual(report["budget"]["stop_reason"], "action_budget")

    def test_state_budget_is_bounded_even_if_new_state_was_observed(self):
        report = self.explore(max_states=1)
        self.assertEqual(len(report["states"]), 1)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["budget"]["stop_reason"], "state_budget")

    def test_scope_escape_aborts_before_any_more_actions(self):
        adapter = DeclarativeAdapter(MODEL)
        original = adapter.observe
        calls = [0]

        def observe():
            calls[0] += 1
            row = original()
            if calls[0] >= 3:
                row["scope"] = "other-app"
            return row

        adapter.observe = observe
        report = explore_interface(adapter, scope="test-app", allowed_actions=["open"])
        self.assertEqual(report["budget"]["stop_reason"], "scope_mismatch")
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["budget"]["actions"], 1)

    def test_unstable_state_identity_cannot_make_graph_complete(self):
        adapter = DeclarativeAdapter(MODEL)
        original = adapter.observe
        calls = [0]

        def observe():
            calls[0] += 1
            row = original()
            if calls[0] == 2:
                row["actions"] = ["open"]
            return row

        adapter.observe = observe
        report = explore_interface(adapter, scope="test-app", allowed_actions=["open"])
        self.assertEqual(report["budget"]["stop_reason"], "unstable_state_identity")

    def test_adapter_timeout_and_error_remain_incomplete(self):
        for error in (TimeoutError("late"), RuntimeError("private details")):
            adapter = DeclarativeAdapter(MODEL)
            adapter.perform = lambda action: (_ for _ in ()).throw(error)
            report = explore_interface(adapter, scope="test-app", allowed_actions=["open"])
            self.assertEqual(report["status"], "incomplete")
            self.assertFalse(report["coverage"]["allowed_frontier_exhausted"])
            self.assertNotIn("private details", json.dumps(report))

    def test_late_callback_is_discarded(self):
        ticks = iter([0, 0, 0, 0, 20, 20])
        with patch("skills.app_test.explorer.time.monotonic", side_effect=lambda: next(ticks)):
            report = self.explore(max_seconds=1)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["states"], [])
        self.assertEqual(report["budget"]["stop_reason"], "duration_budget")

    def test_invalid_observation_and_action_result_are_not_success(self):
        for field, value in (("actions", ["open", "open"]), ("terminal", "false"), ("state_id", "")):
            adapter = DeclarativeAdapter(MODEL)
            original = adapter.observe
            adapter.observe = lambda: {**original(), field: value}
            report = explore_interface(adapter, scope="test-app", allowed_actions=["open"])
            self.assertEqual(report["budget"]["stop_reason"], "invalid_observation")
        adapter = DeclarativeAdapter(MODEL)
        adapter.perform = lambda action: {"status": "passed"}
        report = explore_interface(adapter, scope="test-app", allowed_actions=["open"])
        self.assertEqual(report["budget"]["stop_reason"], "invalid_action_result")

    def test_input_validation_and_no_mutation_of_caller_model(self):
        baseline = json.dumps(MODEL)
        self.explore()
        self.assertEqual(json.dumps(MODEL), baseline)
        for kwargs in ({"max_actions": True}, {"max_states": 0}, {"max_seconds": float("nan")},
                       {"allowed_actions": ["open", "open"]}, {"scope": "bad\nname"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.explore(**kwargs)
        for model in ({}, {"scope": "a", "initial_state": "x", "states": {"x": {"actions": {"go": "missing"}}}}):
            with self.assertRaises(ValueError):
                DeclarativeAdapter(model)


class HttpNavigationTests(unittest.TestCase):
    def setUp(self):
        self.requests.clear()

    @classmethod
    def setUpClass(cls):
        cls.requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                cls.requests.append(self.path)
                pages = {
                    "/": ('home', '<a data-action="open" href="/form">Open form</a>'
                          '<a data-action="broken" href="/missing">Broken</a>'
                          '<a data-action="external" href="http://example.invalid/">Outside</a>'
                          '<a data-action="redirect" href="/redirect">Redirect</a>'),
                    "/form": ('form', '<a data-action="submit" href="/done">Submit</a>'
                              '<a data-action="back" href="/">Back</a>'),
                    "/done": ('done', '<meta name="parcimonia-terminal" content="true">Success'),
                }
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://example.invalid/")
                    self.end_headers()
                    return
                if self.path not in pages:
                    self.send_error(404)
                    return
                state, body = pages[self.path]
                payload = ('<!doctype html><html><head><meta name="parcimonia-state" content="'
                           + state + '"><meta name="parcimonia-scope" content="live-app"></head>'
                           '<body>' + body + '</body></html>').encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def adapter(self):
        return LoopbackHttpAdapter(self.origin + "/", scope="live-app",
                                   allowed_paths=["/", "/form", "/done", "/missing", "/redirect"])

    def test_actual_local_html_interface_and_independent_state_assertion(self):
        adapter = self.adapter()
        report = explore_interface(adapter, scope="live-app", allowed_actions=["open", "submit", "back"],
                                   goals=["done", "not-linked"])
        self.assertEqual(report["status"], "completed")
        self.assertEqual({(edge["source"], edge["action"], edge["target"])
                          for edge in report["transitions"]},
                         {("home", "open", "form"), ("form", "submit", "done"), ("form", "back", "home")})
        self.assertEqual(report["coverage"]["goals_not_observed"], ["not-linked"])
        self.assertEqual(report["adapter_kind"], "http_navigation")
        self.assertFalse(report["boundaries"]["graphical_qualification"])
        # Independent of traversal's report: drive the known target directly.
        adapter.reset()
        adapter.perform("open")
        adapter.perform("submit")
        self.assertEqual(adapter.observe()["state_id"], "done")
        self.assertTrue(adapter.observe()["terminal"])
        self.assertNotIn("/missing", self.requests)

    def test_actual_broken_link_is_retained_as_failed_transition(self):
        report = explore_interface(self.adapter(), scope="live-app", allowed_actions=["broken"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["transitions"][0]["reason"], "http_status_404")

    def test_external_link_and_redirect_are_not_followed(self):
        for action in ("external", "redirect"):
            adapter = self.adapter()
            report = explore_interface(adapter, scope="live-app", allowed_actions=[action])
            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(report["budget"]["stop_reason"], "adapter_error")

    def test_origin_and_path_validation_including_ipv6(self):
        for url in ("https://127.0.0.1/", "http://example.invalid/", "http://localhost/",
                    "http://192.168.1.1/", "http://user:pass@127.0.0.1/", "http://127.0.0.1/?x=1",
                    "http://127.0.0.1/#frag", "http://127.0.0.1:99999/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                LoopbackHttpAdapter(url, scope="x", allowed_paths=["/"])
        ipv6 = LoopbackHttpAdapter("http://[::1]:1234/", scope="x", allowed_paths=["/"])
        self.assertEqual(ipv6.origin, ("http", "::1", 1234))
        adapter = self.adapter()
        adapter.reset()
        for url in (self.origin + "/other", self.origin + "/form?x=1", "http://127.0.0.2/form"):
            with self.assertRaises(ValueError):
                adapter._validate_url(url)
        with self.assertRaises(ValueError):
            LoopbackHttpAdapter(self.origin + "/", scope="x", allowed_paths=["/form"])


if __name__ == "__main__":
    unittest.main()
