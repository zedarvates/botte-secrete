"""Experimental, non-executing copy of memory arguments from exact query spans.

This binds a separately supplied proposal; it neither selects spans nor runs a
model. Valid coordinates do not establish the correct tool or user intent.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from skills.memory_hub.shared_contract import decode, encode, validate
from .base import ToolRouteResult
from .memory_pilot import catalog_sha256, memory_tools

CONTRACT_VERSION = "botte.memory-argument-spans/v1"
SOURCE = "argument_spans_candidate"
MAX_QUERY_BYTES = 512
MAX_INPUT_BYTES = 8192
BOUNDARY = {"executed": False, "activation_allowed": False,
            "tool_calls_executed": 0, "memory_writes": 0,
            "successful_action_ledger_eligible": False}


def query_sha256(query):
    """Fingerprint the exact UTF-8 query; never strip or normalize its contents."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("invalid_query")
    data = query.encode("utf-8")
    if len(data) > MAX_QUERY_BYTES:
        raise ValueError("query_too_large")
    return hashlib.sha256(data).hexdigest()


def bind_argument_spans(query, proposal):
    """Copy half-open Unicode code-point spans into existing memory schemas.

    A producer must echo the host's query digest to reject stale proposals.
    This is source correlation, not authentication or execution authorization.
    All invalid inputs abstain. Confidence is unmeasured and remains zero.
    """
    abstain = lambda reason: ToolRouteResult.abstain(SOURCE, reason)
    try:
        expected_hash = query_sha256(query)
    except ValueError:
        return abstain("invalid_query")
    fields = {"schema_version", "query_sha256", "tool_name", "argument_spans"}
    if not isinstance(proposal, dict) or set(proposal) != fields:
        return abstain("invalid_span_proposal")
    if proposal["schema_version"] != CONTRACT_VERSION:
        return abstain("unsupported_span_contract")
    if proposal["query_sha256"] != expected_hash:
        return abstain("query_digest_mismatch")
    spans, tool_name = proposal["argument_spans"], proposal["tool_name"]
    if not isinstance(spans, dict):
        return abstain("invalid_argument_spans")
    if tool_name is None:
        return abstain("model_abstained" if not spans else "abstention_with_arguments")
    tools = {tool.name: tool for tool in memory_tools()}
    if not isinstance(tool_name, str) or tool_name not in tools:
        return abstain("tool_not_allowed")
    schema = tools[tool_name].parameters
    if set(spans) - set(schema["properties"]):
        return abstain("unexpected_argument")
    arguments = {}
    for name, span in spans.items():
        if not isinstance(span, dict) or set(span) != {"start", "end"}:
            return abstain("invalid_argument_span")
        start, end = span["start"], span["end"]
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(query)):
            return abstain("invalid_argument_span")
        arguments[name] = query[start:end]
    try:
        validate(schema, arguments)
    except (ValueError, TypeError, KeyError, OverflowError):
        return abstain("invalid_arguments")
    return ToolRouteResult(tool_name, arguments, SOURCE, 0.0, False, "advisory_only")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output exists")
        with args.input.open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input too large")
        request = decode(raw)
        if not isinstance(request, dict) or set(request) != {"query", "proposal"}:
            raise ValueError("expected query and proposal only")
        route = bind_argument_spans(request["query"], request["proposal"])
        valid = route.reason in {"advisory_only", "model_abstained"}
        result = {
            "schema_version": "botte.memory-argument-spans-result/v1",
            "mode": "candidate_advisory",
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "binder_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "catalog_sha256": catalog_sha256(),
            "valid_proposal": valid, "route": asdict(route),
            "confidence_kind": "not_measured",
            "new_inference_attempts": 0, "model_quality_measured": False,
            "limitations": ["producer_must_use_unicode_code_point_offsets",
                            "span_and_tool_selection_correctness_not_established",
                            "negation_and_user_authorization_not_evaluated",
                            "no_integration_with_the_frozen_model_adapters"],
            **BOUNDARY,
        }
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
        print(encode({"valid_proposal": valid, "reason": route.reason,
                      "new_inference_attempts": 0, **BOUNDARY}).decode("utf-8"))
        return 0 if valid else 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(encode({"error": type(error).__name__, "detail": str(error)[:160],
                      **BOUNDARY}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
