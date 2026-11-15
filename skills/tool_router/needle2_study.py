"""Frozen, advisory-only Needle calibration and local-generalist comparison.

No discovery, tool dispatch, memory writes, retries, or activation decisions.
The validation split requires a selection recorded on the calibration split.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import time
import urllib.parse
import urllib.request

from skills.memory_hub.shared_contract import decode, encode, validate
from .base import ToolRouteResult
from .memory_pilot import catalog_sha256, memory_tools
from .needle2_adapter import Needle2ToolRouter

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs/validation/needle2-study-protocol-v1.json"
LIMIT = 65_536
BOUNDARY = {"executed": False, "activation_allowed": False,
            "tool_calls_executed": 0, "memory_writes": 0,
            "successful_action_ledger_eligible": False}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return decode(Path(path).read_bytes())


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")


def load_protocol(path=PROTOCOL):
    data = Path(path).read_bytes()
    protocol = decode(data)
    if protocol["catalog_sha256"] != catalog_sha256():
        raise ValueError("catalog changed; create a new study version")
    for name, expected in protocol["source_sha256"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError("study source changed: " + name)
    splits, queries, ids = {}, set(), set()
    specs = {t.name: t for t in memory_tools()}
    for split, info in protocol["splits"].items():
        raw = (ROOT / info["path"]).read_bytes()
        if digest(raw) != info["sha256"]:
            raise ValueError("dataset changed: " + split)
        cases = [decode(line) for line in raw.splitlines() if line.strip()]
        if len(cases) != 20 or sum(c["expected_tool"] is not None for c in cases) != 10:
            raise ValueError("expected 10 positive and 10 negative cases per split")
        for case in cases:
            if not isinstance(case["id"], str) or not case["id"] or case["id"] in ids:
                raise ValueError("case identifiers must be unique across splits")
            query = case["query"]
            if not isinstance(query, str) or not query.strip() or len(query.encode("utf-8")) > 512:
                raise ValueError("invalid query")
            normalized = " ".join(query.casefold().split())
            if normalized in queries:
                raise ValueError("duplicate query across splits")
            ids.add(case["id"])
            queries.add(normalized)
            tool = case["expected_tool"]
            if tool is None:
                if case["expected_arguments"] != {}:
                    raise ValueError("negative case has arguments")
            else:
                validate(specs[tool].parameters, case["expected_arguments"])
        splits[split] = cases
    return protocol, digest(data), splits


def summarize(rows, threshold=0):
    accepted = [r for r in rows if not r["abstained"] and r["route"]["confidence"] >= threshold]
    positives = [r for r in rows if r["positive"]]
    negatives = [r for r in rows if not r["positive"]]
    exact = [r for r in accepted if r["positive"] and r["call_correct"]]
    timings = sorted(r["latency_ms"] for r in rows)
    return {"threshold": threshold, "positive_cases": len(positives),
            "negative_cases": len(negatives), "proposals": len(accepted),
            "positive_exact_calls": len(exact),
            "positive_wrong_proposals": sum(r["positive"] and not r["call_correct"] for r in accepted),
            "negative_proposals": sum(not r["positive"] for r in accepted),
            "exact_proposal_precision": len(exact) / len(accepted) if accepted else None,
            "positive_exact_coverage": len(exact) / len(positives) if positives else None,
            "tools_with_exact_calls": sorted({r["route"]["tool_name"] for r in exact}),
            "by_tool": {t.name: sum(r["route"]["tool_name"] == t.name for r in exact) for t in memory_tools()},
            "first_request_ms": rows[0]["latency_ms"] if rows else None,
            "p95_roundtrip_ms": timings[math.ceil(.95 * len(timings)) - 1] if timings else None,
            "runtime_errors": sum(r.get("runtime_error", False) for r in rows)}


def generalist_route(text):
    """No JSON repair or argument normalization; use the memory contract."""
    try:
        obj = decode(text.encode("utf-8"))
        if not isinstance(obj, dict) or set(obj) != {"tool_name", "arguments"}:
            raise ValueError("invalid output envelope")
        if obj["tool_name"] is None and obj["arguments"] == {}:
            return ToolRouteResult.abstain("generalist", "model_abstained")
        spec = next(t for t in memory_tools() if t.name == obj["tool_name"])
        validate(spec.parameters, obj["arguments"])
        return ToolRouteResult(spec.name, obj["arguments"], "generalist", 1, False, "advisory_only")
    except (ValueError, TypeError, KeyError, StopIteration):
        return ToolRouteResult.abstain("generalist", "invalid_model_output")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirects are disabled")


class Generalist:
    """Explicit loopback/private-IP chat endpoint; never uses proxy settings."""
    def __init__(self, config):
        url = urllib.parse.urlsplit(config["base_url"])
        if url.scheme not in {"http", "https"} or url.username or url.password or url.query or url.fragment:
            raise ValueError("invalid local base URL")
        if url.path not in {"", "/", "/v1", "/v1/"}:
            raise ValueError("base URL must end at /v1 or the server root")
        host = url.hostname
        if host != "localhost":
            address = ipaddress.ip_address(host)
            networks = [ipaddress.ip_network(n) for n in
                        ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")]
            if not any(address in network for network in networks):
                raise ValueError("only loopback and private LAN addresses are allowed")
        self.model = config["model"]
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("an explicit model identifier is required")
        for name in ("weights_sha256", "quantization", "runtime_version"):
            if not isinstance(config.get(name), str) or not config[name].strip():
                raise ValueError("model provenance required: " + name)
        if len(config["weights_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in config["weights_sha256"]):
            raise ValueError("weights_sha256 must identify the installed weights")
        self.url = urllib.parse.urlunsplit((url.scheme, url.netloc, "/v1/chat/completions", "", ""))
        self.timeout = config.get("timeout_seconds", 30)
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or not 0 < self.timeout <= 60:
            raise ValueError("timeout must be in (0, 60]")
        self.headers = {"Content-Type": "application/json"}
        if config.get("api_key_env"):
            key = os.environ.get(config["api_key_env"])
            if not key:
                raise ValueError("configured authentication environment variable is missing")
            self.headers["Authorization"] = "Bearer " + key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.runtime = {k: config[k] for k in ("model", "weights_sha256", "quantization", "runtime_version")}
        self.runtime["provenance"] = "operator_supplied_not_independently_attested"
        self.last = {}

    def route(self, query, tools):
        self.last = {}
        system = ("Select at most one listed memory tool for the current user request. "
                  "Do not execute anything. Abstain for negation, missing required information, "
                  "write requests, identity changes, ambiguity or requests outside the catalog. "
                  'Return only JSON: {"tool_name": name, "arguments": {...}}; '
                  'for abstention return {"tool_name": null, "arguments": {}}. '
                  "Preserve argument text exactly. Catalog: " +
                  json.dumps([t.as_dict() for t in tools], ensure_ascii=False, separators=(",", ":")))
        body = {"model": self.model, "messages": [{"role": "system", "content": system},
                {"role": "user", "content": query}], "temperature": 0, "max_tokens": 256,
                "stream": False, "response_format": {"type": "json_object"}}
        raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = urllib.request.Request(self.url, data=raw, headers=self.headers, method="POST")
        with self.opener.open(request, timeout=self.timeout) as response:
            response_raw = response.read(LIMIT + 1)
        if len(response_raw) > LIMIT:
            raise ValueError("response exceeds limit")
        payload = decode(response_raw)
        if payload.get("model") != self.model:
            raise ValueError("server returned a different model identity")
        choices = payload["choices"]
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ValueError("completion did not finish normally")
        message = choices[0]["message"]
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError("unexpected native tool call in JSON-response mode")
        content = message["content"]
        if not isinstance(content, str):
            raise ValueError("content must be JSON text")
        self.last = {"request_sha256": digest(raw), "response_sha256": digest(response_raw)}
        return generalist_route(content)


def checked_report(path, protocol, protocol_hash, splits):
    report = read_json(path)
    if (report.get("schema_version") != "botte.needle2-study-run/v1"
            or report["protocol_sha256"] != protocol_hash or report.get("complete") is not True):
        raise ValueError("report is incomplete or belongs to another protocol")
    split = report["split"]
    if report["dataset_sha256"] != protocol["splits"][split]["sha256"]:
        raise ValueError("report dataset differs")
    if [r["id"] for r in report["cases"]] != [c["id"] for c in splits[split]]:
        raise ValueError("report case set or order differs")
    if any(report.get(k) != v for k, v in BOUNDARY.items()):
        raise ValueError("report crossed the advisory boundary")
    if any(r.get("runtime_error") for r in report["cases"]):
        raise ValueError("runtime failures are not quality evidence")
    specs = {t.name: t for t in memory_tools()}
    for row, case in zip(report["cases"], splits[split]):
        route = row["route"]
        tool, arguments, confidence = route["tool_name"], route["arguments"], route["confidence"]
        if route.get("executable") is not False:
            raise ValueError("executable route in study evidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("invalid recorded confidence")
        if tool is not None:
            validate(specs[tool].parameters, arguments)
        elif arguments != {}:
            raise ValueError("abstention with arguments")
        expected = {"positive": case["expected_tool"] is not None, "abstained": tool is None,
                    "tool_correct": tool == case["expected_tool"],
                    "call_correct": tool == case["expected_tool"] and arguments == case["expected_arguments"]}
        if any(row[k] is not v for k, v in expected.items()):
            raise ValueError("recorded scoring differs from the frozen labels")
    return report


def select(report, thresholds):
    if report["backend"] != "needle" or report["split"] != "calibration":
        raise ValueError("selection requires Needle calibration results")
    curve = [summarize(report["cases"], t) for t in thresholds]
    eligible = [m for m in curve if m["positive_exact_calls"] and
                m["positive_wrong_proposals"] == 0 and m["negative_proposals"] == 0]
    best = max(eligible, key=lambda m: (m["positive_exact_calls"], m["threshold"])) if eligible else None
    useful = best is not None and best["positive_exact_calls"] >= 5 and len(best["tools_with_exact_calls"]) >= 3
    return {"decision": "candidate_for_validation" if useful else "stop_insufficient_safe_coverage",
            "selected_threshold": best["threshold"] if useful else None,
            "best_diagnostic_threshold": best["threshold"] if best else None,
            "curve": curve, "selection_is_authorization": False, **BOUNDARY}


def collect(args, protocol, protocol_hash, splits):
    output = args.output
    journal = output.with_suffix(output.suffix + ".jsonl")
    if output.exists() or journal.exists():
        raise ValueError("output or journal exists; inspect it, do not rerun blindly")
    selection_hash, selected_threshold = None, None
    if args.split == "validation":
        if not args.selection or not args.calibration:
            raise ValueError("validation requires --selection and --calibration")
        prior = checked_report(args.calibration, protocol, protocol_hash, splits)
        frozen = read_json(args.selection)
        expected = {**select(prior, protocol["thresholds"]), "protocol_sha256": protocol_hash,
                    "calibration_sha256": digest(args.calibration.read_bytes())}
        if frozen != expected or frozen["decision"] != "candidate_for_validation":
            raise ValueError("calibration did not qualify this frozen selection")
        selection_hash = digest(args.selection.read_bytes())
        selected_threshold = frozen["selected_threshold"]
    if args.backend == "needle":
        if not args.library or not args.engine_python:
            raise ValueError("explicit Needle library and interpreter required")
        if digest(args.library.read_bytes()) != protocol["needle_library_sha256"]:
            raise ValueError("Needle library does not match the frozen study")
        router = Needle2ToolRouter(args.library, python_executable=args.engine_python, confidence_threshold=0)
    else:
        if not args.generalist_config:
            raise ValueError("explicit --generalist-config required")
        router = Generalist(read_json(args.generalist_config))
    rows = []
    report = {"schema_version": "botte.needle2-study-run/v1", "protocol_sha256": protocol_hash,
              "dataset_sha256": protocol["splits"][args.split]["sha256"], "split": args.split,
              "backend": args.backend, "selection_sha256": selection_hash,
              "selected_threshold": selected_threshold,
              "recorded_at": datetime.now(timezone.utc).isoformat(), "cases": rows,
              "complete": False, "case_attempts": 0, "runtime": {},
              "corpus": "authored_synthetic_not_independent_user_task_evidence", **BOUNDARY}
    try:
        with journal.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({k: v for k, v in report.items() if k != "cases"}) + "\n")
            handle.flush()
            for case in splits[args.split]:
                started, failed = time.perf_counter(), False
                try:
                    route = router.route(case["query"], memory_tools())
                    failed = route.reason in {"needle2_runtime_error", "needle2_timeout", "needle2_library_missing"}
                except (OSError, ValueError, TypeError, KeyError, IndexError):
                    route, failed = ToolRouteResult.abstain(args.backend, "runtime_error"), True
                row = {"id": case["id"], "kind": case["kind"], "positive": case["expected_tool"] is not None,
                       "tool_correct": route.tool_name == case["expected_tool"],
                       "call_correct": route.tool_name == case["expected_tool"] and dict(route.arguments) == case["expected_arguments"],
                       "abstained": route.abstained, "route": asdict(route), "runtime_error": failed,
                       "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
                if args.backend == "generalist":
                    row.update(router.last)
                rows.append(row)
                report["case_attempts"] += 1
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                if failed:
                    break
    finally:
        if args.backend == "needle":
            report["runtime"] = {"worker": router.worker_runtime, "library_sha256": router.library_sha256,
                                 "platform": platform.system(), "architecture": platform.machine(),
                                 "host_python": platform.python_version(), "startup_ms": router.startup_ms}
            router.close()
        else:
            report["runtime"] = router.runtime
        report["complete"] = len(rows) == len(splits[args.split]) and not any(r["runtime_error"] for r in rows)
        report["summary"] = summarize(rows)
        write_json(output, report)
    return report


def compare(needle, generalist):
    if needle["backend"] != "needle":
        raise ValueError("--needle requires native Needle evidence")
    if generalist is not None:
        if generalist["backend"] != "generalist" or any(needle[k] != generalist[k] for k in
            ("protocol_sha256", "dataset_sha256", "split", "selection_sha256")):
            raise ValueError("comparison requires identical protocol, dataset, split and selection")
    return {"schema_version": "botte.needle2-study-comparison/v1", "protocol_sha256": needle["protocol_sha256"],
            "split": needle["split"], "needle_diagnostic": summarize(needle["cases"]),
            "needle_selected": summarize(needle["cases"], needle["selected_threshold"])
                if needle.get("selected_threshold") is not None else None,
            "generalist": summarize(generalist["cases"]) if generalist else "not_measured",
            "paired_comparison_measured": generalist is not None,
            "speedup_claim_allowed": False,
            "limitations": ["synthetic_small_sample", "no_end_to_end_fallback_measurement",
                            "native_peak_memory_not_measured", "no_homelab_claim_from_this_report"], **BOUNDARY}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--backend", choices=("needle", "generalist"), required=True)
    run.add_argument("--split", choices=("calibration", "validation"), required=True)
    run.add_argument("--library", type=Path)
    run.add_argument("--engine-python")
    run.add_argument("--generalist-config", type=Path)
    run.add_argument("--selection", type=Path)
    run.add_argument("--calibration", type=Path)
    choice = sub.add_parser("select")
    choice.add_argument("--calibration", type=Path, required=True)
    comp = sub.add_parser("compare")
    comp.add_argument("--needle", type=Path, required=True)
    comp.add_argument("--generalist", type=Path)
    for cmd in (run, choice, comp):
        cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        protocol, protocol_hash, splits = load_protocol()
        if args.output.exists():
            raise ValueError("output exists")
        if args.command == "run":
            result = collect(args, protocol, protocol_hash, splits)
        elif args.command == "select":
            report = checked_report(args.calibration, protocol, protocol_hash, splits)
            result = {**select(report, protocol["thresholds"]), "protocol_sha256": protocol_hash,
                      "calibration_sha256": digest(args.calibration.read_bytes())}
            write_json(args.output, result)
        else:
            needle = checked_report(args.needle, protocol, protocol_hash, splits)
            generalist = checked_report(args.generalist, protocol, protocol_hash, splits) if args.generalist else None
            result = compare(needle, generalist)
            write_json(args.output, result)
        print(encode({k: v for k, v in result.items() if k not in {"cases", "curve"}}).decode("utf-8"))
        return 3 if result.get("complete") is False else 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(encode({"error": type(error).__name__, "detail": str(error)[:160], **BOUNDARY}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
