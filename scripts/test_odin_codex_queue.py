"""Acceptance: admission, durable restart, lifecycle races and loopback boundary."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from odin_queue.codex import CodexEngine, SimulationEngine
from odin_queue.server import Service, make_http
from odin_queue.state import OCCUPIED, Queue, SupervisorLock

FAKE = Path(__file__).parent / "odin_queue" / "fixtures" / "fake_codex.py"


def wait_for(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("Condition not reached")


class QueueFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = []
        for i in range(12):
            folder = self.root / f"repo-{i}"
            folder.mkdir()
            self.paths.append(str(folder))
        self.queue = Queue(self.root / "queue.json", [self.root])

    def tearDown(self):
        self.temp.cleanup()

    def add(self, number, path=None, prompt="hold-test", thread_id=None):
        return self.queue.submit(title=f"Discussion {number}", prompt=prompt,
                                 cwd=path or self.paths[number], dedupe_key=f"job-{number}", thread_id=thread_id)


class QueueTests(QueueFixture):
    def test_five_claims_under_concurrent_admission_and_live_numbering(self):
        for i in range(8):
            self.add(i)
        with ThreadPoolExecutor(max_workers=20) as pool:
            claims = [result for result in pool.map(lambda _: self.queue.claim(), range(20)) if result]
        self.assertEqual(len(claims), 5)
        self.assertEqual(len({j["id"] for j in claims}), 5)
        pending = [j for j in self.queue.snapshot()["jobs"] if j["status"] == "queued"]
        self.assertEqual([j["queue_position"] for j in pending], [1, 2, 3])
        self.queue.event(claims[0]["id"], "complete", status="completed")
        sixth = self.queue.claim()
        self.assertEqual(sixth["id"], pending[0]["id"])
        pending = [j for j in self.queue.snapshot()["jobs"] if j["status"] == "queued"]
        self.assertEqual([j["queue_position"] for j in pending], [1, 2])
        self.assertEqual(self.queue.snapshot()["occupied"], 5)

    def test_parent_child_locks_do_not_block_independent_folder(self):
        parent = Path(self.paths[0]); child = parent / "nested"; child.mkdir()
        first = self.add(0)
        second = self.add(1, str(child))
        third = self.add(2)
        self.assertEqual(self.queue.claim()["id"], first["id"])
        self.assertEqual(self.queue.claim()["id"], third["id"])
        self.assertIsNone(self.queue.claim())
        self.assertTrue(next(j for j in self.queue.snapshot()["jobs"] if j["id"] == second["id"])["workspace_busy"])
        self.queue.event(first["id"], "complete", status="completed")
        self.assertEqual(self.queue.claim()["id"], second["id"])

    def test_same_thread_is_locked_even_in_distinct_workspaces(self):
        first = self.add(0, thread_id="existing-thread")
        self.add(1, thread_id="existing-thread")
        self.assertEqual(self.queue.claim()["id"], first["id"])
        self.assertIsNone(self.queue.claim())

    def test_retry_is_idempotent_and_divergent_retry_rejected(self):
        first = self.add(0)
        self.assertEqual(self.add(0)["id"], first["id"])
        with self.assertRaises(ValueError):
            self.add(0, prompt="different")
        reopened = Queue(self.root / "queue.json", [self.root])
        self.assertEqual(len(reopened.snapshot()["jobs"]), 1)
        self.assertEqual(reopened.submit(title="Discussion 0", prompt="hold-test", cwd=self.paths[0], dedupe_key="job-0")["id"], first["id"])

    def test_restart_keeps_unknown_slots_and_does_not_replay(self):
        first = self.add(0); self.add(1)
        self.queue.claim()
        reopened = Queue(self.root / "queue.json", [self.root])
        self.assertEqual(reopened.snapshot()["occupied"], 1)
        self.assertIsNone(reopened.claim())
        with self.assertRaises(ValueError):
            reopened.confirm_stopped(first["id"], False)
        reopened.confirm_stopped(first["id"], True)
        self.assertIsNotNone(reopened.claim())

    def test_waiting_approval_and_cancellation_keep_slot_until_completion(self):
        jobs = [self.add(i) for i in range(6)]
        for _ in range(5): self.queue.claim()
        self.queue.attach(jobs[0]["id"], thread_id="thread", turn_id="turn")
        self.queue.event(jobs[0]["id"], "approval", request={"id": 99})
        self.assertIsNone(self.queue.claim())
        self.assertEqual(self.queue.cancel(jobs[0]["id"])["status"], "cancelling")
        self.queue.event(jobs[0]["id"], "resolved", request_id=99)
        self.assertIsNone(self.queue.claim())
        self.queue.event(jobs[0]["id"], "complete", status="interrupted")
        self.assertEqual(self.queue.claim()["id"], jobs[5]["id"])

    def test_queued_cancel_renumbers_and_pause_does_not_interrupt(self):
        first = self.add(0); self.add(1)
        self.queue.pause(True)
        self.assertIsNone(self.queue.claim())
        self.queue.cancel(first["id"])
        self.assertEqual(self.queue.snapshot()["jobs"][1]["queue_position"], 1)
        self.queue.pause(False)
        self.assertIsNotNone(self.queue.claim())

    def test_paths_capacity_and_mode_are_guarded(self):
        with self.assertRaises(ValueError): Queue(self.root / "bad.json", [self.root], capacity=6)
        with self.assertRaises(ValueError): Queue(self.root / "bad.json", [self.root], capacity=True)
        with self.assertRaises(ValueError): self.add(0, str(self.root.parent))
        with self.assertRaises(ValueError): self.add(0, "relative")
        self.add(0)
        with self.assertRaises(ValueError): Queue(self.root / "queue.json", [self.root], mode="codex")

    def test_late_events_cannot_resurrect_completed_jobs(self):
        job = self.add(0); self.queue.claim()
        self.queue.event(job["id"], "complete", status="completed")
        self.queue.attach(job["id"], thread_id="thread", turn_id="turn")
        self.queue.event(job["id"], "approval", request={"id": 9})
        self.assertEqual(self.queue.snapshot()["occupied"], 0)

    def test_two_supervisors_cannot_own_one_spool(self):
        with SupervisorLock(self.root / "supervisor.lock"):
            with self.assertRaises(RuntimeError):
                with SupervisorLock(self.root / "supervisor.lock"):
                    self.fail("second supervisor admitted")
        with SupervisorLock(self.root / "supervisor.lock"):
            pass


class PersistenceTests(QueueFixture):
    def test_rejected_submission_cannot_be_claimed_after_storage_recovers(self):
        for target, error in [
            ("os.replace", OSError("replace failed")),
            ("os.fsync", OSError("fsync failed")),
            ("tempfile.NamedTemporaryFile", OSError("temporary file failed")),
            ("json.dump", TypeError("serialization failed")),
        ]:
            with self.subTest(target=target):
                self.queue = Queue(self.root / (target + ".json"), [self.root])
                before = self.queue.snapshot()
                with patch("odin_queue.state." + target, side_effect=error):
                    with self.assertRaises(OSError):
                        self.add(0)
                self.assertEqual(self.queue.snapshot(), before)
                self.assertFalse(self.queue.path.exists())
                self.assertEqual(list(self.root.glob(".queue-*")), [])
                with self.assertRaises(OSError):
                    self.queue.claim()
                reopened = Queue(self.queue.path, [self.root])
                self.assertEqual(reopened.snapshot()["jobs"], [])
                self.assertIsNone(reopened.claim())

    def test_failed_transitions_keep_last_committed_state_and_occupied_slots(self):
        transitions = ["claim", "attach", "approval", "resolved", "message",
                       "complete", "unknown", "cancel_queued", "cancel_running",
                       "confirm_stopped", "pause", "resume"]
        for name in transitions:
            with self.subTest(transition=name):
                self.queue = Queue(self.root / (name + ".json"), [self.root])
                job = self.add(0)
                job_id = job["id"]
                if name not in {"claim", "cancel_queued", "pause", "resume"}:
                    self.queue.claim()
                if name not in {"claim", "attach", "cancel_queued", "pause", "resume"}:
                    self.queue.attach(job_id, thread_id="thread", turn_id="turn")
                if name == "resolved":
                    self.queue.event(job_id, "approval", request={"id": 7})
                if name == "confirm_stopped":
                    self.queue.event(job_id, "unknown")
                if name == "resume":
                    self.queue.pause(True)
                actions = {
                    "claim": self.queue.claim,
                    "attach": lambda: self.queue.attach(job_id, thread_id="new-thread", turn_id="new-turn"),
                    "approval": lambda: self.queue.event(job_id, "approval", request={"id": 7}),
                    "resolved": lambda: self.queue.event(job_id, "resolved", request_id=7),
                    "message": lambda: self.queue.event(job_id, "message", text="new result"),
                    "complete": lambda: self.queue.event(job_id, "complete", status="completed"),
                    "unknown": lambda: self.queue.event(job_id, "unknown"),
                    "cancel_queued": lambda: self.queue.cancel(job_id),
                    "cancel_running": lambda: self.queue.cancel(job_id),
                    "confirm_stopped": lambda: self.queue.confirm_stopped(job_id, True),
                    "pause": lambda: self.queue.pause(True),
                    "resume": lambda: self.queue.pause(False),
                }
                before = self.queue.snapshot()
                persisted = self.queue.path.read_bytes()
                with patch("odin_queue.state.os.replace", side_effect=OSError("disk unavailable")):
                    with self.assertRaises(OSError):
                        actions[name]()
                self.assertEqual(self.queue.snapshot(), before)
                self.assertEqual(self.queue.path.read_bytes(), persisted)
                with self.assertRaises(OSError):
                    self.queue.claim()
                with self.assertRaises(OSError):
                    self.add(1)
                self.assertEqual(self.queue.snapshot(), before)

    def test_claim_retains_an_earlier_committed_rejection_if_next_write_fails(self):
        first = self.add(0)
        second = self.add(1)
        Path(self.paths[0]).rmdir()
        replace = os.replace
        calls = []

        def fail_second_replace(source, destination):
            calls.append(destination)
            if len(calls) == 2:
                raise OSError("second write failed")
            return replace(source, destination)

        with patch("odin_queue.state.os.replace", side_effect=fail_second_replace):
            with self.assertRaises(OSError):
                self.queue.claim()
        current = {job["id"]: job for job in self.queue.snapshot()["jobs"]}
        self.assertEqual(current[first["id"]]["status"], "failed")
        self.assertEqual(current[second["id"]]["status"], "queued")
        reopened = Queue(self.queue.path, [self.root])
        self.assertEqual(reopened.snapshot(), self.queue.snapshot())

    def test_failed_recovery_leaves_occupied_work_for_a_later_restart(self):
        job = self.add(0)
        self.queue.claim()
        persisted = self.queue.path.read_bytes()
        with patch("odin_queue.state.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                Queue(self.queue.path, [self.root])
        self.assertEqual(self.queue.path.read_bytes(), persisted)
        reopened = Queue(self.queue.path, [self.root])
        self.assertEqual(reopened.snapshot()["jobs"][0]["id"], job["id"])
        self.assertEqual(reopened.snapshot()["jobs"][0]["status"], "unknown")
        self.assertIsNone(reopened.claim())


class AdapterTests(QueueFixture):
    def setUp(self):
        super().setUp()
        self.engine = CodexEngine(self.queue, [sys.executable, str(FAKE)], timeout=3)

    def tearDown(self):
        self.engine.close()
        super().tearDown()

    def test_api_account_cannot_launch_paid_provider(self):
        with self.assertRaisesRegex(RuntimeError, "connexion ChatGPT"):
            CodexEngine(self.queue, [sys.executable, str(FAKE), "--api-account"], timeout=3)
        self.assertEqual(self.queue.snapshot()["occupied"], 0)

    def _assert_start_write_failure(self, failure_number, expected_turn_starts):
        self.add(0)
        job = self.queue.claim()
        replace = os.replace
        writes = []

        def fail_selected_write(source, destination):
            writes.append(destination)
            if len(writes) == failure_number:
                raise OSError("disk unavailable")
            return replace(source, destination)

        with patch.object(self.engine.rpc, "call", wraps=self.engine.rpc.call) as rpc:
            with patch("odin_queue.state.os.replace", side_effect=fail_selected_write):
                self.engine.start(job)
        self.assertEqual(sum(call.args[0] == "turn/start" for call in rpc.call_args_list), expected_turn_starts)
        self.assertFalse(self.engine.ready)
        self.assertEqual(self.queue.snapshot()["occupied"], 1)
        self.assertEqual(self.queue.snapshot()["jobs"][0]["status"], "starting")
        with self.assertRaises(OSError):
            self.queue.claim()
        with self.assertRaises(OSError):
            self.engine.answer(job["id"], 1, "accept")
        reopened = Queue(self.queue.path, [self.root])
        self.assertEqual(reopened.snapshot()["jobs"][0]["status"], "unknown")
        self.assertIsNone(reopened.claim())

    def test_thread_persistence_failure_prevents_turn_start(self):
        self._assert_start_write_failure(1, 0)

    def test_turn_persistence_failure_keeps_slot_and_does_not_retry(self):
        self._assert_start_write_failure(2, 1)

    def _assert_storage_failure_between_start_phases(self, after_thread):
        self.add(0)
        job = self.queue.claim()
        target = self.queue if after_thread else self.engine
        method = "attach" if after_thread else "_check_account"
        original = getattr(target, method)

        def finish_phase_then_fail_storage(*args, **kwargs):
            result = original(*args, **kwargs)
            with patch("odin_queue.state.os.replace", side_effect=OSError("concurrent write failed")):
                with self.assertRaises(OSError):
                    self.queue.pause(True)
            return result

        with patch.object(self.engine.rpc, "call", wraps=self.engine.rpc.call) as rpc:
            with patch.object(target, method, side_effect=finish_phase_then_fail_storage):
                self.engine.start(job)
        methods = [call.args[0] for call in rpc.call_args_list]
        self.assertEqual(methods.count("thread/start"), int(after_thread))
        self.assertNotIn("turn/start", methods)
        self.assertFalse(self.engine.ready)
        self.assertEqual(self.queue.snapshot()["occupied"], 1)
        self.assertEqual(self.queue.snapshot()["jobs"][0]["status"], "starting")

    def test_failure_after_account_check_prevents_starting_thread(self):
        self._assert_storage_failure_between_start_phases(False)

    def test_failure_after_thread_attach_prevents_starting_turn(self):
        self._assert_storage_failure_between_start_phases(True)

    def test_actual_stdio_completion_before_response_does_not_resurrect(self):
        job = self.add(0, prompt="auto-test")
        self.engine.start(self.queue.claim())
        current = self.queue.snapshot()["jobs"][0]
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["result"], "Test result")
        self.assertEqual(self.queue.snapshot()["occupied"], 0)

    def test_transport_timeout_is_unknown_not_retried(self):
        self.engine.rpc.timeout = 0.3
        self.add(0, prompt="timeout-test"); self.add(1)
        self.engine.start(self.queue.claim())
        self.assertEqual(self.queue.snapshot()["jobs"][0]["status"], "unknown")
        self.assertIsNone(self.queue.claim())

    def test_approval_requires_single_owner_decision_and_stale_reply_fails(self):
        job = self.add(0, prompt="approval-test")
        self.engine.start(self.queue.claim())
        current = wait_for(lambda: self.queue.snapshot()["jobs"][0] if self.queue.snapshot()["jobs"][0]["pending"] else None)
        self.assertEqual(current["status"], "waiting_approval")
        request_id = current["pending"][0]["id"]
        with self.assertRaises(ValueError): self.engine.answer(job["id"], request_id, "acceptForSession")
        self.engine.answer(job["id"], request_id, "decline")
        wait_for(lambda: self.queue.snapshot()["jobs"][0]["status"] == "completed")
        with self.assertRaises(ValueError): self.engine.answer(job["id"], request_id, "accept")

    def test_interrupt_acknowledgement_alone_keeps_slot(self):
        job = self.add(0, prompt="ack-only-test")
        self.engine.start(self.queue.claim())
        self.engine.cancel(self.queue.cancel(job["id"]))
        self.assertEqual(self.queue.snapshot()["jobs"][0]["status"], "cancelling")
        self.assertEqual(self.queue.snapshot()["occupied"], 1)

    def test_unsupported_requests_are_not_automatically_approved(self):
        job = self.add(0, prompt="unsupported-test")
        self.engine.start(self.queue.claim())
        current = wait_for(lambda: self.queue.snapshot()["jobs"][0] if self.queue.snapshot()["jobs"][0]["pending"] else None)
        self.assertFalse(current["pending"][0]["supported"])
        with self.assertRaises(ValueError): self.engine.answer(job["id"], current["pending"][0]["id"], "accept")
        self.engine.cancel(self.queue.cancel(job["id"]))
        wait_for(lambda: self.queue.snapshot()["jobs"][0]["status"] == "interrupted")


class HttpTests(QueueFixture):
    def setUp(self):
        super().setUp()
        self.service = Service(self.queue, SimulationEngine(self.queue, duration=30))
        self.server, self.token = make_http(self.service, port=0)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.service.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        self.service.close(); self.thread.join(timeout=1)
        super().tearDown()

    def request(self, path, data=None, headers=None):
        default = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        if headers: default.update(headers)
        request = Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=default)
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def test_host_origin_and_authentication_boundaries(self):
        for headers, code in [({"Authorization":""},401), ({"Origin":"https://evil.example"},403), ({"Host":"evil.example"},403)]:
            with self.assertRaises(HTTPError) as error: self.request("/api/state", headers=headers)
            self.assertEqual(error.exception.code, code)
        with self.assertRaises(HTTPError): self.request("/api/anything", {"command":"arbitrary"})

    def test_storage_failure_returns_503_and_stops_admission_until_restart(self):
        self.queue.pause(True)
        persisted = self.queue.path.read_bytes()
        with patch("odin_queue.state.os.replace", side_effect=OSError("private-spool-path")):
            with self.assertRaises(HTTPError) as error:
                self.request("/api/jobs", {"title": "Rejected", "prompt": "inspect only",
                                          "cwd": self.paths[0], "dedupe_key": "rejected"})
        self.assertEqual(error.exception.code, 503)
        self.assertNotIn("private-spool-path", error.exception.read().decode("utf-8"))
        wait_for(lambda: not self.service.thread.is_alive())
        current = self.request("/api/state")
        self.assertEqual(current["jobs"], [])
        self.assertTrue(current["supervisor_error"])
        self.assertEqual(self.queue.path.read_bytes(), persisted)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/control", {"paused": False})
        self.assertEqual(error.exception.code, 503)
        self.assertTrue(self.request("/api/state")["paused"])

    def test_http_demo_has_five_running_and_badges_renumber(self):
        self.request("/api/demo", {"dedupe_key":"demo"})
        snap = wait_for(lambda: self.request("/api/state") if self.request("/api/state")["occupied"] == 5 else None)
        self.assertEqual(snap["mode"], "simulation")
        self.assertEqual([j["queue_position"] for j in snap["jobs"] if j["status"] == "queued"], [1,2,3])
        active = next(j for j in snap["jobs"] if j["status"] == "running")
        self.request("/api/jobs/" + active["id"] + "/cancel", {})
        wait_for(lambda: self.request("/api/state")["queued"] == 2)
        self.assertEqual([j["queue_position"] for j in self.request("/api/state")["jobs"] if j["status"] == "queued"], [1,2])


def main(argv=None):
    result = unittest.main(module=__name__, argv=argv, verbosity=2, exit=False).result
    failed = len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)
    skipped = len(result.skipped) + len(result.expectedFailures)
    passed = max(0, result.testsRun - failed - skipped)
    print(f"RESULT: {passed} passed, {failed} failed, {skipped} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
