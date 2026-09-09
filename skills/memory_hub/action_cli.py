"""Capture, recall, or execute a plan with the shared action memory."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.conductor.verified import MAX_REPORT, read_document
from skills.memory_hub.action_memory import capture_report, recall_for_plan, run_with_memory


def configured_client(url=None, token_file=None):
    from skills.memory_hub.shared_http import MemoryHTTPClient, read_token
    url = url or os.environ.get("BOTTE_MEMORY_URL")
    token_file = token_file or os.environ.get("BOTTE_MEMORY_TOKEN_FILE")
    if not url or not token_file:
        raise ValueError("configure BOTTE_MEMORY_URL and BOTTE_MEMORY_TOKEN_FILE for the shared service")
    return MemoryHTTPClient(url, read_token(Path(token_file)))


def dispatch(operation, args, client=None):
    """Host-side adapter. Authentication identity is supplied by configuration."""
    modes = {"capture": {"report", "visibility"}, "recall": {"limit"},
             "run": {"visibility", "checkpoint", "confirm", "dry_run", "resume", "timeout"}}
    if operation not in modes:
        raise ValueError("unknown action-memory operation")
    allowed = {"plan", "project", "project_id"} | modes[operation]
    if set(args) - allowed:
        raise ValueError("unknown action-memory arguments")
    plan = args["plan"]
    common = {"project_root": args.get("project", "."), "project_id": args["project_id"]}
    if operation == "run" and args.get("dry_run", True) is True:
        # A preview does not need a configured client, read a token or call the API.
        return run_with_memory(plan, None, **common, checkpoint=args.get("checkpoint"),
                               dry_run=True, confirm=args.get("confirm", False),
                               resume=args.get("resume", False), timeout=args.get("timeout", 120))
    client = client or configured_client()
    if operation == "recall":
        return recall_for_plan(plan, client, **common, limit=args.get("limit", 3))
    if operation == "capture":
        return capture_report(plan, args["report"], client, **common,
                              visibility=args.get("visibility", "private"))
    if operation == "run":
        return run_with_memory(plan, client, **common, checkpoint=args.get("checkpoint"),
                               dry_run=args.get("dry_run", True), confirm=args.get("confirm", False),
                               resume=args.get("resume", False), timeout=args.get("timeout", 120),
                               visibility=args.get("visibility", "private"))
    raise ValueError("unknown action-memory operation")


def main(argv=None):
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["recall", "capture", "run"])
    parser.add_argument("--plan", required=True)
    parser.add_argument("--project", default=".")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--report")
    parser.add_argument("--checkpoint")
    parser.add_argument("--visibility", choices=["private", "project"], default="private")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    if args.operation == "capture" and not args.report:
        parser.error("capture requires --report; use the immutable archive for retries")
    if args.operation == "run" and not args.checkpoint:
        parser.error("run requires --checkpoint")
    if args.operation != "capture" and args.report:
        parser.error("--report requires capture")
    if args.operation != "run" and (args.execute or args.confirm or args.resume or args.checkpoint):
        parser.error("execution flags require run")
    try:
        payload = {"plan": read_document(args.plan), "project": args.project, "project_id": args.project_id}
        if args.operation == "run":
            payload.update(visibility=args.visibility, checkpoint=args.checkpoint, dry_run=not args.execute,
                           confirm=args.confirm, resume=args.resume, timeout=args.timeout)
        if args.operation == "capture":
            payload.update(report=read_document(args.report, limit=MAX_REPORT), visibility=args.visibility)
        result = dispatch(args.operation, payload)
        code = 0
        if args.operation == "capture":
            code = 0 if result["complete"] else 1
        if args.operation == "run" and args.execute:
            code = 0 if result["execution"].get("complete") and result["memory_after"].get("complete") else 1
    except Exception as error:
        result, code = {"error_type": type(error).__name__, "error": str(error)}, 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
