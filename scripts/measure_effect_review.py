"""Compare serialized planning context. No workflow execution or model calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skills.capabilities.review import METHOD
from skills.conductor import plan

GOALS = (
    "audit my project and report metrics",
    "inspect verified outcome history",
    "reduce token cost and route local models",
)


def size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def recovery_details(compact: dict) -> dict:
    """Fixed serialization example, not an operation-suitability evaluation."""
    from skills.llm_mcp.server import TOOLS, handle
    definition = next(tool for tool in TOOLS if tool["name"] == "effect_details")
    exchanges = 0
    calls = 0
    for step in compact["steps"]:
        review = step["review_before"]
        if review["declaration"] != "declared":
            continue
        request = {"jsonrpc": "2.0", "id": calls + 1, "method": "tools/call", "params": {
            "name": "effect_details", "arguments": {"source": review["source"],
                "selectors": ["/preconditions", "/required_scope", "/retry"],
                "expected_sha256": review["declaration_sha256"]}}}
        response = handle(request)
        if response.get("error") or response["result"].get("isError"):
            raise ValueError("detail read failed during comparison")
        detail = json.loads(response["result"]["content"][0]["text"])
        if detail["selection_status"] != "selected":
            raise ValueError("declaration changed or became unavailable during comparison")
        exchanges += size(request) + size(response)
        calls += 1
    schema_bytes = size(definition) if calls else 0
    return {"calls": calls, "tool_schema_bytes": schema_bytes,
            "request_response_bytes": exchanges, "additional_bytes": schema_bytes + exchanges}


def measure() -> dict:
    method_bytes = len((ROOT / METHOD).read_bytes())
    rows = []
    for goal in GOALS:
        ordinary = plan(goal)
        full = plan(goal, include_effects=True)
        compact = plan(goal, review_effects=True)
        selected = lambda report: [(s["capability"], s["command"]) for s in report["steps"]]
        if not selected(ordinary) == selected(full) == selected(compact):
            raise ValueError("catalog changed during comparison")
        plain_bytes, full_bytes, compact_bytes = map(size, (ordinary, full, compact))
        total = compact_bytes + method_bytes
        details = recovery_details(compact)
        with_details = total + details["additional_bytes"]
        rows.append({"goal": goal, "steps": len(compact["steps"]),
                     "ordinary_bytes": plain_bytes, "full_effects_bytes": full_bytes,
                     "compact_bytes": compact_bytes, "compact_with_method_bytes": total,
                     "reduction_vs_full_percent": round(100 * (1 - total / full_bytes), 1),
                     "overhead_vs_ordinary_bytes": total - plain_bytes,
                     "recovery_details": details, "with_recovery_details_bytes": with_details,
                     "with_details_reduction_vs_full_percent": round(100 * (1 - with_details / full_bytes), 1)})
    return {"measurement": "UTF-8 bytes of compact JSON plus shared instructions once per workflow",
            "limits": "Planning and fixed recovery-detail examples only; no model tokens, downstream task quality or execution costs measured. Other detail reads add context; these fields are not a sufficient operation review.",
            "method_bytes": method_bytes, "workflows": rows}


if __name__ == "__main__":
    print(json.dumps(measure(), ensure_ascii=False, indent=2))
