"""LLM-guided runtime setup and explicit execution, with JSON outputs."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.llm_backends.runtime import capture, execute
from skills.llm_backends.runtime_contract import (
    CONTEXT, SCHEMA, TASKS, digest, inspect_local, load, plan, template, validate_config,
)
from skills.llm_backends.runtime_io import RuntimeFailure
from skills.memory_hub.shared_contract import encode


def main(argv=None):
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    make = subs.add_parser("template", help="Generate an offline, non-executable draft")
    make.add_argument("--topology", choices=["single", "local-draft", "remote-draft"], default="single")
    make.add_argument("--memory", choices=["none", "botte_http", "external"], default="none")
    make.add_argument("--output", help="Create a new private file; never overwrite")
    subs.add_parser("schema", help="Configuration, task and external-context JSON Schemas")
    subs.add_parser("inspect", help="Read inventory of this host only; no network scan")
    for name in ("validate", "plan", "run", "benchmark", "capture"):
        sub = subs.add_parser(name)
        sub.add_argument("config", help="Local configuration JSON")
        if name == "plan":
            sub.add_argument("--task", default="chat")
            sub.add_argument("--profile")
        if name in {"run", "benchmark"}:
            sub.add_argument("--task" if name == "run" else "--tasks", required=True,
                             help="Task object for run, array of tasks for benchmark")
            sub.add_argument("--context", help="Authorized external context packet")
            sub.add_argument("--record-memory", action="store_true", help="Capture the outbox after execution")
        if name in {"run", "benchmark", "capture"}:
            sub.add_argument("--run-dir", required=True,
                             help="New private directory, or an existing one for capture-only retries")
        if name == "benchmark":
            sub.add_argument("--profiles", nargs="+", required=True, help="Direct baseline first, then candidates")
            sub.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        command = args.command
        if command == "template":
            result = template(args.topology, args.memory)
            if args.output:
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(encode(result).decode("utf-8") + "\n")
                result = {"path": str(path.resolve()), "state": "draft"}
        elif command == "schema":
            result = {"config": SCHEMA, "tasks": TASKS, "context": CONTEXT}
        elif command == "inspect":
            result = inspect_local()
        else:
            config = validate_config(load(args.config))
            if command == "validate":
                result = {"valid": True, "state": config["state"], "config_sha256": digest(config),
                          "capability_status": "declared_unverified", "network_calls": 0}
            elif command == "plan":
                result = plan(config, args.task, args.profile)
            elif command == "capture":
                result = capture(config, args.run_dir)
            else:
                if args.record_memory and config["memory"]["adapter"] != "botte_http":
                    raise ValueError("--record-memory requires the botte_http adapter")
                tasks = [load(args.task)] if command == "run" else load(args.tasks)
                result = execute(config, tasks, args.run_dir,
                                 profile_ids=args.profiles if command == "benchmark" else None,
                                 repetitions=args.repetitions if command == "benchmark" else 1,
                                 external_context=load(args.context) if args.context else None)
                if args.record_memory:
                    capture(config, args.run_dir)
                print(encode(result).decode("utf-8"))
                return 0 if all(o["status"] == "completed" for o in result["observations"]) else 1
        print(encode(result).decode("utf-8"))
        return 0
    except (ValueError, OSError, RuntimeFailure) as error:
        # Do not echo OS paths, input text, endpoint bodies or credentials.
        message = str(error) if isinstance(error, (ValueError, RuntimeFailure)) else "local_file_operation_failed"
        print(encode({"error": message}).decode("utf-8"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
