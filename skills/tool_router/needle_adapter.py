"""Optional adapter for needle-rs; it fails closed when unavailable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .base import ToolRouteResult, ToolSpec, validate_route

MAX_TOOLS = 10
MAX_INPUT_TOKENS = 1024


def estimate_tokens(value: str) -> int:
    return (len(value) + 3) // 4


class NeedleToolRouter:
    """Route with Needle only when its optional runtime and assets are present."""

    def __init__(self, weights_path: str | Path | None = None, vocab_path: str | Path | None = None, *, engine: Any = None):
        self.engine = engine
        self.unavailable_reason: str | None = None
        if engine is not None:
            return
        if weights_path is None or vocab_path is None:
            self.unavailable_reason = "needle_assets_not_configured"
            return
        if not Path(weights_path).is_file() or not Path(vocab_path).is_file():
            self.unavailable_reason = "needle_assets_missing"
            return
        try:
            import needle_rs  # type: ignore[import-not-found]
        except ImportError:
            self.unavailable_reason = "needle_runtime_unavailable"
            return
        try:
            self.engine = needle_rs.Needle(str(weights_path), str(vocab_path))
        except (AttributeError, OSError, RuntimeError, ValueError):
            self.unavailable_reason = "needle_initialization_failed"

    def route(self, query: str, tools: Sequence[ToolSpec]) -> ToolRouteResult:
        if self.engine is None:
            return ToolRouteResult.abstain("needle", self.unavailable_reason or "needle_unavailable")
        if len(tools) > MAX_TOOLS:
            return ToolRouteResult.abstain("needle", "too_many_tools")
        payload = json.dumps([tool.as_dict() for tool in tools], ensure_ascii=False, separators=(",", ":"))
        if estimate_tokens(query + payload) > MAX_INPUT_TOKENS:
            return ToolRouteResult.abstain("needle", "input_too_large")
        try:
            raw = self.engine.route(query, payload)
            response = json.loads(raw if isinstance(raw, str) else raw.text)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return ToolRouteResult.abstain("needle", "invalid_model_response")
        if not isinstance(response, dict):
            return ToolRouteResult.abstain("needle", "invalid_model_response")
        return validate_route(response.get("tool_name"), response.get("arguments", {}), tools, source="needle", confidence=response.get("confidence", 0.0))
