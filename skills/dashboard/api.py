"""Local-first dashboard HTTP server.

The server binds to loopback by default. Use ``--host`` explicitly when a LAN
binding is intended and protected by the surrounding network boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from skills.decision_ladder.metrics import LadderMetrics
from skills.universal_compressor.compressor import stats as compressor_stats
from skills.auto_memory.hook import memory_stats


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_SUMMARY_PATH = REPO_ROOT / ".botte-cache" / "test-summary.json"


def load_test_summary(path: str | Path | None = None) -> dict:
    """Load the latest test-run summary without inventing a fallback count."""
    summary_path = Path(path) if path is not None else TEST_SUMMARY_PATH
    empty = {
        "passed": None,
        "failed": None,
        "suite_count": None,
        "partial": False,
        "status": "not_run",
        "generated_at": None,
        "git_sha": None,
        "stale": False,
    }
    if not summary_path.is_file():
        return empty
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        passed = data.get("passed")
        failed = data.get("failed")
        if not isinstance(passed, int) or not isinstance(failed, int):
            return {**empty, "status": "invalid"}
        generated_at = data.get("generated_at")
        age_seconds = max(0.0, time.time() - summary_path.stat().st_mtime)
        partial = bool(data.get("partial"))
        status = "partial" if partial else str(data.get("status", "unknown"))
        return {
            "passed": passed,
            "failed": failed,
            "suite_count": data.get("suite_count"),
            "partial": partial,
            "status": status,
            "generated_at": generated_at,
            "git_sha": data.get("git_sha"),
            "stale": age_seconds > 7 * 24 * 60 * 60,
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {**empty, "status": "invalid"}


def load_memory_hub_metrics(base_dir: str | Path | None = None) -> dict:
    """Aggregate governed Memory Hub assets without exposing their contents."""
    root = Path(base_dir) if base_dir is not None else Path(
        os.environ.get("BOTTE_MEMORY_HUB_DIR", Path.home() / ".botte" / "memory_hub")
    )
    result = {"entries": 0, "projects": 0, "by_status": {}, "by_asset": {}}
    if not root.is_dir():
        return result
    try:
        from skills.memory_hub.store import MemoryStore

        with MemoryStore(base_dir=root) as store:
            projects = store.list_projects()
            result["projects"] = len(projects)
            for project_id in projects:
                stats = store.stats(project_id)
                result["entries"] += int(stats["total"])
                for key, value in stats["by_status"].items():
                    result["by_status"][key] = result["by_status"].get(key, 0) + value
                for key, value in stats["by_asset"].items():
                    result["by_asset"][key] = result["by_asset"].get(key, 0) + value
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error):
        result["status"] = "unavailable"
    return result


def load_metrics(*, test_summary_path: str | Path | None = None,
                 memory_hub_dir: str | Path | None = None) -> dict:
    """Load metrics from all sources."""
    # Load decision ladder metrics
    dl = LadderMetrics.load()
    tests = load_test_summary(test_summary_path)
    dl_dict = {
        "tests_passed": tests["passed"],
        "tests_failed": tests["failed"],
        "tests_status": tests["status"],
        "tests_partial": tests["partial"],
        "tests_stale": tests["stale"],
        "tests_updated_at": tests["generated_at"],
        "tests_git_sha": tests["git_sha"],
        "test_suites": tests["suite_count"],
        "lines_saved": dl.total_lines_saved,
        "avoidable_pct": dl.avoidable_pct,
        "total_tasks": dl.total_checks,
        "by_rung": dl.by_rung,
    }

    # Compressor stats
    cs = compressor_stats()
    dl_dict["compressor"] = cs

    # Governed memory plus legacy AutoMemory during the migration window.
    hub = load_memory_hub_metrics(memory_hub_dir)
    legacy = memory_stats()
    dl_dict["memory_entries"] = hub["entries"]
    dl_dict["memory_projects"] = hub["projects"]
    dl_dict["memory_by_status"] = hub["by_status"]
    dl_dict["memory_by_asset"] = hub["by_asset"]
    dl_dict["legacy_memory_entries"] = legacy.get("total_entries", 0)
    dl_dict["generated_at"] = time.time()

    return dl_dict


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/stats":
            try:
                body = json.dumps(load_metrics(), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception:
                body = json.dumps({"error": "metrics_unavailable"}).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
        elif path in ("/", "/index.html"):
            html = Path(__file__).parent / "index.html"
            self._send(200, html.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found\n", "text/plain; charset=utf-8")


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), DashboardHandler)


def run_server(port: int = 8765, host: str = "127.0.0.1"):
    server = make_server(host, port)
    print(f"Dashboard API running on http://{host}:{server.server_port}")
    server.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Serve the local Botte dashboard")
    parser.add_argument("--host", default=os.environ.get("BOTTE_DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    run_server(port=args.port, host=args.host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
