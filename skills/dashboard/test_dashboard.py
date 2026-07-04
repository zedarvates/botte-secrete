"""Tests for dashboard skill."""
import json
import threading
import time
import urllib.request
from skills.dashboard.api import load_metrics, run_server, DashboardHandler


class TestLoadMetrics:
    def test_load_metrics_returns_dict(self):
        m = load_metrics()
        assert isinstance(m, dict)
        assert "tests_passed" in m
        assert "lines_saved" in m
        assert "by_rung" in m


class TestAPI:
    @classmethod
    def setup_class(cls):
        cls.server_thread = None

    def test_handler_paths(self):
        # Just verify the handler exists
        assert DashboardHandler
        assert callable(load_metrics)