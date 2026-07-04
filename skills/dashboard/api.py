"""
API endpoint for dashboard — serves stats as JSON.

Usage:
    python -m skills.dashboard.api
    # GET /api/stats → {tests_passed, lines_saved, by_rung, memory_entries, ...}
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from skills.decision_ladder.metrics import LadderMetrics
from skills.universal_compressor.compressor import stats as compressor_stats
from skills.auto_memory.hook import memory_stats


METRICS_PATH = Path.home() / ".botte" / "metrics.json"


def load_metrics() -> dict:
    """Load metrics from all sources."""
    # Load decision ladder metrics
    dl = LadderMetrics.load()
    dl_dict = {
        "tests_passed": 138 + dl.total_checks,  # base count + new
        "lines_saved": dl.total_lines_saved,
        "avoidable_pct": dl.avoidable_pct,
        "total_tasks": dl.total_checks,
        "by_rung": dl.by_rung,
    }

    # Compressor stats
    cs = compressor_stats()
    dl_dict["compressor"] = cs

    # Memory stats
    ms = memory_stats()
    dl_dict["memory_entries"] = ms.get("total_entries", 0)
    dl_dict["memory_by_category"] = ms.get("by_category", {})

    return dl_dict


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet

    def do_GET(self):
        if self.path == "/api/stats":
            data = load_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/" or self.path == "/index.html":
            html = Path(__file__).parent / "index.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()


def run_server(port: int = 8765):
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard API running on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()