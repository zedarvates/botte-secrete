"""Isolated subprocess adapter for opt-in cooperative effect observations."""

from __future__ import annotations

import argparse
import json
import runpy
import shlex
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

from skills.capabilities.effects import _read_bounded, _unique_object
from skills.capabilities.observations import (
    MAX_REPORT_BYTES, ObservationSession, empty_report, validate_report,
)

MODULES = {f"skills.{name}.cli" for name in
           ("checkup", "infra_advisor", "llm_backends", "cluster")}


def command_parts(command: str) -> list[str]:
    # Preserve the executor's existing parsing rules.
    return [p.strip('"') for p in shlex.split(command, posix=False)]


def read_checkpoint(path: Path, run_id: str) -> dict:
    try:
        report = json.loads(_read_bounded(path, MAX_REPORT_BYTES).decode("utf-8"),
                            object_pairs_hook=_unique_object)
        if validate_report(report) or report["run_id"] != run_id:
            raise ValueError("invalid report")
        return report
    except (OSError, ValueError, TypeError, RecursionError, RuntimeError):
        report = empty_report(run_id)
        report["problems"].append("checkpoint missing or invalid; effects remain unknown")
        return report


def run_observed(command: str, cwd: str, timeout: int, runner=None) -> tuple[int, str, dict]:
    """Return process evidence independently of the child-written call report."""
    report = empty_report()
    if runner is not None:
        with ObservationSession(run_id=report["run_id"]) as session:
            try:
                code, out = runner(command, cwd, timeout)
            except Exception:
                session.report["process"] = {"status": "runner_error", "exit_code": -1}
                session.problem("injected runner raised; inspect recorded partial effects before retry")
                return -1, "injected runner raised", session.report
        session.report["process"] = {"status": "exited", "exit_code": code}
        session.problem("injected runner: only synchronous instrumented calls were observed")
        return code, out, session.report
    parts = command_parts(command)
    if len(parts) < 3 or parts[0] != "python" or parts[1] != "-m" or parts[2] not in MODULES:
        from skills.conductor.executor import _default_runner
        code, out = _default_runner(command, cwd, timeout)
        report["process"] = {"status": "exited" if code != -1 else "runner_error", "exit_code": code}
        report["problems"].append("command has no observation adapter; effects remain unknown")
        return code, out, report
    with tempfile.TemporaryDirectory(prefix="botte-effects-") as temporary:
        checkpoint = Path(temporary) / "observations.json"
        launch = [sys.executable, "-m", "skills.conductor.observed_run",
                  "--checkpoint", str(checkpoint), "--run-id", report["run_id"],
                  "--module", parts[2], "--", *parts[3:]]
        try:
            proc = subprocess.run(launch, cwd=cwd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
            code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
            status = "exited"
        except subprocess.TimeoutExpired:
            code, out, status = -1, f"timeout after {timeout}s", "timed_out"
        except OSError:
            code, out, status = -1, "could not launch observed command", "launch_failed"
        report = read_checkpoint(checkpoint, report["run_id"])
        # Parent evidence is authoritative about its process, never about all
        # grandchildren or remote work that may outlive it.
        report["process"] = {"status": status, "exit_code": code}
        if status != "exited" or any(c["status"] == "running" for c in report["calls"]):
            report["problems"].append("execution incomplete; recorded effects may be partial or ongoing")
        return code, out, report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--module", choices=sorted(MODULES), required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    # The caller owns this private temporary destination. Never accept report
    # paths or executable verification text from effects declarations.
    skill_dir = Path(find_spec(args.module).origin).resolve().parent
    sys.argv = [args.module, *(args.args[1:] if args.args[:1] == ["--"] else args.args)]
    with ObservationSession(run_id=args.run_id, checkpoint=args.checkpoint) as session:
        with session.call(skill_dir, "cli"):
            try:
                runpy.run_module(args.module, run_name="__main__", alter_sys=True)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
