"""Behavioral acceptance for shared RAM budgets; no real workload is launched."""
from datetime import datetime, timezone
import json
import io
import multiprocessing
import os
from pathlib import Path, PurePosixPath
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skills.host_resources import GiB, HostMemoryGuard, probe_memory, _cgroup_v2, main


def sample(available=8 * GiB, total=16 * GiB, commit=None, source="linux"):
    return {"total_bytes": total, "available_bytes": available,
            "commit_available_bytes": commit, "commit_required": source == "windows",
            "source": source, "measured_monotonic": time.monotonic(),
            "measured_at_utc": datetime.now(timezone.utc).isoformat()}


def simultaneous_claim(path, key, start, result):
    guard = HostMemoryGuard(path, probe=sample)
    start.wait(timeout=10)
    result.put(guard.reserve(key, 4 * GiB)["allowed"])


def posix_files(files):
    """Model Linux paths without consulting the test runner's native OS flavour."""
    class FixturePath(PurePosixPath):
        def read_text(self, *, encoding):
            if encoding != "utf-8":
                raise AssertionError("fixture reads must use UTF-8")
            return files[str(self)]

        def exists(self):
            return str(self) in files

    return FixturePath


class HostMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "shared.json"
        self.guard = HostMemoryGuard(self.path, probe=sample)

    def tearDown(self):
        self.temp.cleanup()

    def test_budget_blocks_second_job_and_release_reopens_admission(self):
        first = self.guard.reserve("queue-A:job-1", 4 * GiB)
        self.assertTrue(first["allowed"])
        second = HostMemoryGuard(self.path, probe=sample)
        self.assertEqual(second.reserve("queue-B:job-2", 4 * GiB)["reason"], "insufficient_ram")
        self.guard.release("queue-A:job-1")
        self.assertTrue(second.reserve("queue-B:job-2", 4 * GiB)["allowed"])

    def test_reservation_is_idempotent_and_changed_budget_rejected(self):
        self.assertTrue(self.guard.reserve("job", 4 * GiB)["allowed"])
        self.assertTrue(self.guard.reserve("job", 4 * GiB)["allowed"])
        self.assertEqual(self.guard.snapshot()["reserved_bytes"], 4 * GiB)
        self.assertEqual(self.guard.reserve("job", GiB)["reason"], "reservation_conflict")

    def test_commit_headroom_is_required_on_windows(self):
        guard = HostMemoryGuard(self.path, probe=lambda: sample(commit=3 * GiB, source="windows"))
        self.assertEqual(guard.reserve("job", 2 * GiB)["reason"], "insufficient_commit")
        self.assertFalse(self.path.exists())

    def test_missing_commit_measurement_is_not_treated_as_unlimited(self):
        guard = HostMemoryGuard(self.path, probe=lambda: sample(source="windows"))
        self.assertFalse(guard.reserve("job", GiB)["allowed"])

    def test_check_remeasures_low_memory_and_retains_reservation(self):
        self.guard.reserve("job", 4 * GiB)
        self.guard.probe = lambda: sample(available=GiB)
        self.assertEqual(self.guard.check("job")["reason"], "insufficient_ram")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["reservations"]["job"]["requested_bytes"], 4 * GiB)
        self.assertEqual(self.guard.check("missing")["reason"], "reservation_missing")

    def test_owner_can_list_reservations_when_measurement_is_unavailable(self):
        self.guard.reserve("job", 4 * GiB)
        with patch.object(self.guard, "probe", side_effect=OSError("unavailable")):
            result = self.guard.snapshot(include_reservations=True)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["reservations"], [{"key": "job", "requested_bytes": 4 * GiB}])
            self.assertNotIn("reservations", self.guard.snapshot())

    def test_margin_uses_larger_of_fixed_budget_and_ten_percent(self):
        guard = HostMemoryGuard(self.path, probe=lambda: sample(available=10 * GiB, total=64 * GiB))
        self.assertFalse(guard.reserve("job", 4 * GiB)["allowed"])

    def test_invalid_and_stale_measurements_fail_closed(self):
        bad_values = [{"available_bytes": True}, {"available_bytes": -1},
                      {"total_bytes": 0}, {"available_bytes": 20 * GiB},
                      {"measured_monotonic": time.monotonic() - 10},
                      {"measured_monotonic": time.monotonic() + 10},
                      {"measured_monotonic": float("nan")}, {"measured_at_utc": None},
                      {"commit_required": True}, {"source": "unsupported"}]
        for changes in bad_values:
            with self.subTest(changes=changes):
                self.guard.probe = lambda: {**sample(), **changes}
                self.assertFalse(self.guard.reserve("job", GiB)["allowed"])
                self.assertFalse(self.path.exists())
        for invalid in [True, 0, -1, 1.5, float("nan"), None]:
            with self.subTest(budget=invalid):
                self.assertFalse(self.guard.reserve("job", invalid)["allowed"])

    def test_measurement_failure_and_corrupt_state_do_not_reset_budgets(self):
        self.guard.reserve("job", GiB)
        original = self.path.read_bytes()
        with patch.object(self.guard, "probe", side_effect=OSError("probe failed")):
            self.assertFalse(self.guard.reserve("next", GiB)["allowed"])
        self.assertEqual(self.path.read_bytes(), original)
        for malformed in ["{broken", '{"schema_version":true,"reservations":{}}',
                          '{"schema_version":1,"reservations":{},"reservations":{}}',
                          '{"schema_version":1,"reservations":{"x":{"requested_bytes":true}}}']:
            self.path.write_text(malformed, encoding="utf-8")
            self.assertFalse(self.guard.reserve("next", GiB)["allowed"])
            self.assertEqual(self.path.read_text(encoding="utf-8"), malformed)

    def test_write_failure_never_admits_and_release_failure_is_reported(self):
        with patch("skills.host_resources.os.replace", side_effect=OSError("disk unavailable")):
            self.assertFalse(self.guard.reserve("job", GiB)["allowed"])
        self.assertFalse(self.path.exists())
        self.assertFalse(self.guard.reserve("retry", GiB)["allowed"])
        # Separate pristine registry for the release failure case.
        self.path = Path(self.temp.name) / "other.json"
        self.guard = HostMemoryGuard(self.path, probe=sample)
        self.guard.reserve("job", GiB)
        with patch("skills.host_resources.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.guard.release("job")
        self.assertEqual(self.guard.snapshot()["reservation_count"], 1)

    def test_missing_initialized_registry_cannot_silently_forget_reservations(self):
        self.assertTrue(self.guard.reserve("job", 4 * GiB)["allowed"])
        self.path.unlink()
        reopened = HostMemoryGuard(self.path, probe=sample)
        self.assertEqual(reopened.reserve("next", GiB)["reason"], "resource_state_unavailable")

    def test_no_timestamp_or_pid_based_automatic_reclamation(self):
        self.guard.reserve("job", 4 * GiB)
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        doc["reservations"]["job"].update(pid=999999, expires_at=0)
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        reopened = HostMemoryGuard(self.path, probe=sample)
        self.assertFalse(reopened.reserve("next", 4 * GiB)["allowed"])
        self.assertEqual(reopened.snapshot()["reservation_count"], 1)

    def test_simultaneous_processes_share_one_reservation_budget(self):
        context = multiprocessing.get_context("spawn")
        start, results = context.Barrier(4), context.Queue()
        processes = [context.Process(target=simultaneous_claim, args=(str(self.path), str(i), start, results))
                     for i in range(4)]
        try:
            for process in processes:
                process.start()
            accepted = [results.get(timeout=15) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sum(accepted), 1)
            self.assertEqual(self.guard.snapshot()["reserved_bytes"], 4 * GiB)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
            results.close()

    def test_relative_state_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            HostMemoryGuard("relative.json")
        with patch.dict(os.environ, {"BOTTE_RESOURCE_STATE": "relative.json"}):
            with self.assertRaises(ValueError):
                HostMemoryGuard()

    def test_only_explicit_local_snapshot_exposes_reservation_keys(self):
        self.guard.reserve("private-spool:job", GiB)
        self.assertNotIn("reservations", self.guard.snapshot())
        self.assertEqual(self.guard.snapshot(include_reservations=True)["reservations"],
                         [{"key": "private-spool:job", "requested_bytes": GiB}])

    def test_recovery_retains_overbudget_jobs_without_probe_and_never_shrinks(self):
        self.guard.probe = lambda: (_ for _ in ()).throw(OSError("probe unavailable"))
        self.guard.retain_many({"old-unknown": 12 * GiB})
        self.guard.retain_many({"old-unknown": GiB, "old-running": 4 * GiB})
        self.guard.probe = sample
        self.assertEqual(self.guard.snapshot()["reserved_bytes"], 16 * GiB)
        self.assertFalse(self.guard.reserve("new", GiB)["allowed"])
        self.assertFalse(self.guard.check("old-unknown")["allowed"])
        with patch("skills.host_resources.os.replace", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                self.guard.retain_many({"another": GiB})
        self.assertEqual(self.guard.snapshot()["reserved_bytes"], 16 * GiB)

    def test_cli_release_requires_stop_confirmation_and_reports_persistence_failure(self):
        self.guard.reserve("job", GiB)
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                main(["release", "job", "--state", str(self.path)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.guard.snapshot()["reservation_count"], 1)
        with patch("skills.host_resources.os.replace", side_effect=OSError("unavailable")), \
                patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["release", "job", "--state", str(self.path), "--stopped-confirmed"]), 1)
        self.assertEqual(self.guard.snapshot()["reservation_count"], 1)
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(["--state", str(self.path), "release", "job", "--stopped-confirmed"]), 0)
            self.assertTrue(json.loads(output.getvalue())["released"])
        self.assertEqual(self.guard.snapshot()["reservation_count"], 0)


class MemoryProbeTests(unittest.TestCase):
    def test_unsupported_platform_does_not_guess_available_memory(self):
        with patch("skills.host_resources.platform.system", return_value="Other"):
            with self.assertRaises(OSError):
                probe_memory()

    def test_windows_native_probe_reports_physical_and_commit_headroom(self):
        def native_measure(pointer):
            status = pointer._obj
            self.assertEqual(status.length, 64)
            status.total, status.available = 16 * GiB, 8 * GiB
            status.page_available = 5 * GiB
            return 1
        native = SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=native_measure))
        with patch("skills.host_resources.platform.system", return_value="Windows"), \
                patch("skills.host_resources.ctypes.windll", native, create=True):
            measured = probe_memory()
            self.assertEqual(measured["available_bytes"], 8 * GiB)
            self.assertEqual(measured["commit_available_bytes"], 5 * GiB)
            self.assertTrue(measured["commit_required"])

    def test_hidden_cgroup_mount_does_not_admit_against_host_ram(self):
        files = {"/proc/self/cgroup": "0::/\n", "/proc/self/mountinfo": ""}
        with patch("skills.host_resources.Path", posix_files(files)):
            with self.assertRaises(OSError):
                _cgroup_v2(64 * GiB, 32 * GiB)

    def test_hybrid_cgroup_v1_memory_controller_cannot_escape_limits(self):
        files = {"/proc/self/cgroup": "5:memory:/limited\n0::/user.slice\n"}
        with patch("skills.host_resources.Path", posix_files(files)):
            with self.assertRaises(OSError):
                _cgroup_v2(64 * GiB, 32 * GiB)

    def test_linux_requires_memavailable_and_honors_cgroup_ancestors(self):
        files = {"/proc/self/cgroup": "0::/team/worker\n",
                 "/proc/self/mountinfo": "1 2 0:1 / /cgroup rw - cgroup2 cgroup rw\n",
                 "/cgroup/team/worker/memory.max": "max", "/cgroup/team/worker/memory.current": str(GiB),
                 "/cgroup/team/memory.max": str(10 * GiB), "/cgroup/team/memory.current": str(9 * GiB),
                 "/cgroup/memory.max": "max", "/cgroup/memory.current": str(9 * GiB)}
        with patch("skills.host_resources.Path", posix_files(files)):
            self.assertEqual(_cgroup_v2(64 * GiB, 32 * GiB), (10 * GiB, GiB))

    def test_current_cgroup_limit_and_negative_usage_validation(self):
        files = {"/proc/self/cgroup": "0::/\n",
                 "/proc/self/mountinfo": "1 2 0:1 / /cgroup rw - cgroup2 cgroup rw\n",
                 "/cgroup/memory.max": str(4 * GiB), "/cgroup/memory.current": str(3 * GiB)}
        with patch("skills.host_resources.Path", posix_files(files)):
            self.assertEqual(_cgroup_v2(64 * GiB, 32 * GiB), (4 * GiB, GiB))
            files["/cgroup/memory.current"] = "-1"
            with self.assertRaises(ValueError):
                _cgroup_v2(64 * GiB, 32 * GiB)


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    failed = len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)
    skipped = len(result.skipped) + len(result.expectedFailures)
    print(f"RESULT: {result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    raise SystemExit(0 if result.wasSuccessful() else 1)
