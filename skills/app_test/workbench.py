"""Local verification commands. Run ``botte verify --help`` for adapters.

Execution adapters accept explicit trusted local commands only. None of these
commands is a cloud MCP execution endpoint or a claim of GUI qualification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from skills.app_test.process_oracle import invoke_json, read_json, read_json_text
from skills.console_utf8 import force_utf8


def _command(path):
    value = read_json(path)
    from skills.app_test.prioritization import command_fingerprint
    command_fingerprint(value)
    return value


def _process_arguments(parser):
    parser.add_argument("--command-file", required=True, help="JSON array of explicit local argv")
    parser.add_argument("--cwd", type=Path, help="working directory for the trusted oracle")
    parser.add_argument("--timeout", type=float, default=5.0, help="per-process timeout seconds")


def _process_observation(result, **identity):
    keys = ("command_sha256", "exit", "elapsed_ms", "stdout_sha256",
            "stderr_prefix_sha256", "output_hash_covers", "status")
    row = {key: result[key] for key in keys if key in result}
    row.update(identity)
    if isinstance(result.get("reason"), str):
        row["reason"] = result["reason"][:256]
    return row


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="operation", required=True)
    s = sub.add_parser("reduce", help="reduce a JSON list while preserving one failure fingerprint")
    s.add_argument("--input", required=True)
    _process_arguments(s)
    s.add_argument("--max-calls", type=int, default=64)
    s.add_argument("--max-seconds", type=float, default=30)
    s.add_argument("--fingerprint")
    s = sub.add_parser("triage", help="retain bounded attempts with fixed seed/context")
    _process_arguments(s)
    s.add_argument("--context", help="JSON context object; optional")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--attempts", type=int, default=5)
    s.add_argument("--max-seconds", type=float, default=30)
    s = sub.add_parser("mutate", help="test bounded Python mutants in disposable copies")
    s.add_argument("--project", required=True)
    s.add_argument("--source", required=True, help="project-relative Python file")
    s.add_argument("--tests", required=True, nargs="+", help="project-relative test files/directories")
    s.add_argument("--support", nargs="*", default=[])
    s.add_argument("--command-file", help="JSON argv; default: this Python's unittest discovery")
    s.add_argument("--max-mutants", type=int, default=12)
    s.add_argument("--timeout", type=float, default=10)
    s.add_argument("--max-seconds", type=float, default=120)
    s = sub.add_parser("explore", help="explore an explicit model or allowed loopback HTML navigation")
    target = s.add_mutually_exclusive_group(required=True)
    target.add_argument("--model", help="declarative model JSON, labeled model_replay")
    target.add_argument("--origin", help="explicit loopback HTML initial URL")
    s.add_argument("--scope", required=True)
    s.add_argument("--actions", required=True, help="JSON array of allowed action IDs")
    s.add_argument("--paths", help="JSON array of allowed HTTP paths (required for origin)")
    s.add_argument("--goals", help="JSON array of target state IDs")
    s.add_argument("--max-actions", type=int, default=64)
    s.add_argument("--max-states", type=int, default=32)
    s.add_argument("--max-seconds", type=float, default=10)
    s = sub.add_parser("conformance", help="execute supplied Python/cloud helper source comparisons")
    s.add_argument("--cloud-root", required=True)
    s.add_argument("--cases", help="optional bounded JSON case list")
    s.add_argument("--node", default="node")
    s = sub.add_parser("prioritize", help="order supplied checks; does not execute or omit any")
    s.add_argument("--input", required=True, help="JSON with checks [{label,command}] and history")
    s = sub.add_parser("memory", help="preview a verification memory proposal; optionally persist to quarantine")
    s.add_argument("--input", required=True, help="one supported versioned verification report")
    s.add_argument("--project", required=True)
    s.add_argument("--run-id", required=True)
    s.add_argument("--source-uri", required=True)
    s.add_argument("--source-version", required=True)
    s.add_argument("--source-digest", help="optional expected report SHA-256")
    s.add_argument("--documents", help="JSON array of documentary refs with uri/version")
    s.add_argument("--observed-at", type=float, help="optional explicit observation timestamp")
    s.add_argument("--write-quarantine", action="store_true", help="explicitly store a private non-executable observation")
    s.add_argument("--memory-dir", type=Path, help="explicit MemoryStore base directory; required for write")
    s = sub.add_parser("knowledge-links", help="review declared source links and missing/versioned dependencies")
    s.add_argument("--input", required=True, help="versioned knowledge inventory JSON")
    args = p.parse_args(argv)
    try:
        op = args.operation
        if op == "reduce":
            from skills.app_test.reducer import reduce_reproduction
            command = _command(args.command_file)
            process_observations = []

            def oracle(items):
                result = invoke_json(command, items, cwd=args.cwd, timeout_seconds=args.timeout)
                process_observations.append(_process_observation(result,
                                             call_ordinal=len(process_observations) + 1))
                if result.get("status") not in ("failed", "passed", "inconclusive", "error", "timeout"):
                    result = {**result, "status": "inconclusive"}
                return result

            report = reduce_reproduction(read_json(args.input), oracle, max_calls=args.max_calls,
                                         max_seconds=args.max_seconds, expected_fingerprint=args.fingerprint)
            code = 0 if report.get("failure_preserved") else 2
            report["process_adapter"] = {"kind": "explicit_local_json_process",
                "timeout_seconds": args.timeout, "observations": process_observations}
        elif op == "triage":
            from skills.app_test.flaky import triage_failures
            command = _command(args.command_file)
            process_observations = []

            def attempt(index, seed, context_sha256):
                result = invoke_json(command, {"attempt": index, "seed": seed,
                                     "context_sha256": context_sha256}, cwd=args.cwd,
                                     timeout_seconds=args.timeout)
                process_observations.append(_process_observation(result, attempt_index=index))
                if result.get("status") not in ("passed", "failed", "incomplete", "not_run"):
                    result = {**result, "status": "incomplete"}
                return result

            report = triage_failures(attempt, seed=args.seed,
                                      context=read_json(args.context) if args.context else {},
                                      max_attempts=args.attempts, max_seconds=args.max_seconds)
            code = 1 if report.get("failure_ever_reported") else (
                0 if report["classification"] == "no_failure_observed" else 2)
            report["process_adapter"] = {"kind": "explicit_local_json_process",
                "timeout_seconds": args.timeout, "observations": process_observations}
        elif op == "mutate":
            from skills.app_test.mutation import run_mutation_checks
            command = _command(args.command_file) if args.command_file else [
                sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"]
            report = run_mutation_checks(args.project, args.source, test_paths=args.tests,
                         support_paths=args.support, command=command,
                         max_mutants=args.max_mutants, timeout_seconds=args.timeout,
                         max_seconds=args.max_seconds)
            counts = report.get("counts", {})
            code = 2 if report["status"] != "completed" or counts.get("inconclusive", 0) else (
                1 if counts.get("survived", 0) else 0)
        elif op == "explore":
            from skills.app_test.explorer import DeclarativeAdapter, LoopbackHttpAdapter, explore_interface
            if args.model:
                adapter = DeclarativeAdapter(read_json(args.model))
            else:
                if not args.paths:
                    raise ValueError("--origin requires explicit --paths")
                adapter = LoopbackHttpAdapter(args.origin, scope=args.scope,
                                             allowed_paths=read_json(args.paths))
            report = explore_interface(adapter, scope=args.scope, allowed_actions=read_json(args.actions),
                         goals=read_json(args.goals) if args.goals else (),
                         max_actions=args.max_actions, max_states=args.max_states,
                         max_seconds=args.max_seconds)
            code = {"completed": 0, "failed": 1}.get(report["status"], 2)
        elif op == "conformance":
            from skills.preflight.conformance import run_conformance
            report = run_conformance(args.cloud_root, read_json(args.cases) if args.cases else None,
                                     node_command=args.node)
            code = 0 if report["passed"] else 1 if report["status"] == "failed" else 2
        elif op == "memory":
            from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
            if args.write_quarantine != (args.memory_dir is not None):
                raise ValueError("writing needs both --write-quarantine and --memory-dir")
            prepared = prepare_verification_memory(read_json_text(args.input),
                args.project, args.run_id, args.source_uri, args.source_version,
                documentary_refs=read_json(args.documents) if args.documents else (),
                expected_source_digest=args.source_digest, observed_at=args.observed_at)
            if args.write_quarantine:
                from skills.memory_hub.store import MemoryStore
                with MemoryStore(base_dir=args.memory_dir) as store:
                    persisted = persist_to_quarantine(prepared, store)
                report = {"schema": "parcimonia.verification-memory-command/v1",
                          "proposal": prepared, "persistence": persisted}
                code = 0 if persisted.get("status") in ("stored", "already_present") else 2
            else:
                report = prepared
                code = 0
        elif op == "knowledge-links":
            from skills.app_test.knowledge_links import review_knowledge_links
            report = review_knowledge_links(read_json(args.input))
            code = {"completed": 0, "findings": 1}.get(report.get("status"), 2)
        else:
            from skills.app_test.prioritization import prioritize_checks
            payload = read_json(args.input)
            if not isinstance(payload, dict) or not isinstance(payload.get("checks"), list):
                raise ValueError("input needs a checks array")
            checks = [(row["label"], row["command"]) for row in payload["checks"]]
            report = prioritize_checks(checks, payload.get("history", {
                "schema": "parcimonia.test-history/v1", "runs": []}))
            code = 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError, sqlite3.Error) as error:
        report = {"schema": "parcimonia.verification-error/v1", "status": "invalid",
                  "operation": args.operation, "reason": type(error).__name__}
        code = 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
