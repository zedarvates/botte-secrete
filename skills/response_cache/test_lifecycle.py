"""Real disk lifecycle regressions; no model/network providers."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from skills.response_cache import ResponseCache


def test_clear_survives_reopen(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("prompt", "answer", model="m", context="ctx")
    cache.clear()
    assert ResponseCache(str(tmp_path)).get_exact("prompt", "m", "ctx") is None
    assert json.loads(cache.cache_file.read_text(encoding="utf-8")) == {}


def test_expiry_preserves_recent_entries(tmp_path, monkeypatch):
    monkeypatch.setattr("skills.response_cache.time.time", lambda: 1)
    cache = ResponseCache(str(tmp_path))
    cache.set("old", "old answer")
    monkeypatch.setattr("skills.response_cache.time.time", lambda: 10000)
    cache.set("new", "new answer")
    cache.clear(older_than_hours=1)
    reopened = ResponseCache(str(tmp_path))
    assert reopened.get_exact("old") is None
    assert reopened.get_exact("new").response == "new answer"


def test_eviction_applies_to_persisted_merged_state(tmp_path):
    path = tmp_path / "response_cache.json"
    rows = {f"seed-{i}": {"query_hash": f"seed-{i}", "query": f"q{i}", "response": "a",
            "timestamp": i, "hit_count": 0, "model": "", "context_hash": "", "tokens_saved": 0}
            for i in range(1000)}
    path.write_text(json.dumps(rows), encoding="utf-8")
    cache = ResponseCache(str(tmp_path))
    cache.set("fresh", "fresh answer")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1000
    assert "seed-0" not in saved
    assert ResponseCache(str(tmp_path)).get_exact("fresh").response == "fresh answer"


def test_stale_instance_does_not_resurrect_cleared_entries(tmp_path):
    first = ResponseCache(str(tmp_path))
    first.set("old", "answer")
    stale = ResponseCache(str(tmp_path))
    first.clear()
    stale.set("new", "new answer")
    reopened = ResponseCache(str(tmp_path))
    assert reopened.get_exact("old") is None
    assert reopened.get_exact("new").response == "new answer"


def test_miss_observes_another_instance_write(tmp_path):
    first, second = ResponseCache(str(tmp_path)), ResponseCache(str(tmp_path))
    second.set("new", "visible")
    assert first.get_exact("new").response == "visible"


@pytest.mark.parametrize("age", [-1, True, "1", float("inf"), float("nan")])
def test_invalid_expiry_never_clears(tmp_path, age):
    cache = ResponseCache(str(tmp_path))
    cache.set("keep", "answer")
    with pytest.raises(ValueError):
        cache.clear(older_than_hours=age)
    assert cache.get_exact("keep").response == "answer"


def test_parallel_processes_keep_all_entries_and_hit_counts(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("shared", "common", tokens_used=2)
    root = Path(__file__).resolve().parents[2]
    code = """import sys
sys.path.insert(0,sys.argv[1])
from skills.response_cache import ResponseCache
cache=ResponseCache(sys.argv[2])
for i in range(12):
    cache.set(sys.argv[3]+'-'+str(i),'answer')
    assert cache.get_exact('shared').response=='common'
"""
    children = [subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(root), str(tmp_path), str(i)],
                                cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for i in range(4)]
    try:
        for child in children:
            _, errors = child.communicate(timeout=20)
            assert child.returncode == 0, errors.decode("utf-8", errors="replace")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
    report = cache.report()
    assert report["entries"] == 49
    assert report["hits_exact"] == 48
    assert report["tokens_saved_total"] == 96
    assert report["token_savings_basis"] == "caller_reported_usage_not_billing_proof"
    rows = json.loads(cache.cache_file.read_text(encoding="utf-8"))
    assert len(rows) == 49


def test_real_lock_contention_is_bounded(tmp_path):
    root = Path(__file__).resolve().parents[2]
    code = """import sys
sys.path.insert(0,sys.argv[1])
from skills.response_cache import ResponseCache
cache=ResponseCache(sys.argv[2])
with cache._transaction():
    print('locked',flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(root), str(tmp_path)],
                             cwd=tmp_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        assert child.stdout.readline().strip() == "locked"
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            ResponseCache(str(tmp_path))
        assert 1.8 <= time.monotonic() - start <= 5
        child.stdin.write("release\n")
        child.stdin.flush()
        _, errors = child.communicate(timeout=5)
        assert child.returncode == 0, errors
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


def test_invalid_disk_snapshot_cannot_serve_old_memory(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("old", "answer")
    for invalid in ("{", "[]", '{"x":{"timestamp":"wrong"}}'):
        cache.cache_file.write_text(invalid, encoding="utf-8")
        assert cache.get_exact("old") is None


if __name__ == "__main__":
    class Counts:
        passed = failed = 0

        def pytest_runtest_logreport(self, report):
            if report.failed:
                self.failed += 1
            elif report.when == "call" and report.passed:
                self.passed += 1

    counts = Counts()
    code = pytest.main(["--rootdir=.", "-q", __file__], plugins=[counts])
    print(f"RESULT: {counts.passed} passed, {counts.failed} failed")
    raise SystemExit(code)
