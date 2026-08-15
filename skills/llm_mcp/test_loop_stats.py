"""Regression tests for the MCP ``loop_stats`` handler."""

from __future__ import annotations

import json
from unittest.mock import patch

from skills.llm_mcp.server import DISPATCH, handle
from skills.loop_optimizer.ledger import LoopLedger


def test_loop_stats_dispatch_returns_decodable_summary() -> None:
    records = [
        {
            "loop_id": "portfolio-bootstrap",
            "total_tokens": 120,
            "context_tokens": 40,
            "execution_tokens": 50,
            "verification_tokens": 30,
            "cloud_tokens": 20,
            "cache_hit": True,
            "success": True,
        }
    ]

    with patch.object(LoopLedger, "read", return_value=records):
        raw = DISPATCH["loop_stats"]({})

    assert isinstance(raw, str)
    summary = json.loads(raw)
    assert summary == {
        "iterations": 1,
        "tokens_total": 120,
        "context_tokens": 40,
        "execution_tokens": 50,
        "verification_tokens": 30,
        "cloud_tokens": 20,
        "cache_hits": 1,
        "success": True,
    }


def test_loop_stats_is_returned_through_mcp_tools_call() -> None:
    with patch.object(LoopLedger, "read", return_value=[]):
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": 53,
                "method": "tools/call",
                "params": {"name": "loop_stats", "arguments": {}},
            }
        )

    assert response["result"]["content"][0]["type"] == "text"
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["iterations"] == 0
    assert payload["success"] is False
