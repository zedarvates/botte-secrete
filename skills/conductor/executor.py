"""Conductor executor — run the safe steps of a plan, confirm-gate the rest.

The Conductor *plans*; this *runs* the plan. But running arbitrary steps is
risky, so the executor classifies every step and only runs the read-only
analysis ones unattended:

  - SAFE       read-only analysis (audit, metrics, …) → run unattended
  - GATED      mutates state / generates artifacts / escalates to the cloud
               → runs only with confirm=True
  - NEEDS_ARGS the command still has an unfilled <placeholder> → never runs

`dry_run=True` classifies everything and runs nothing — a preview.

Pure stdlib. The local analysis steps it runs cost 0 cloud tokens. The runner
is injectable so the behaviour is testable without spawning subprocesses.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional


# Capabilities whose conductor command is read-only analysis — safe unattended.
SAFE_CAPS = {
    "directives_audit", "metrics", "infra_advisor",
    "checkup", "cluster", "llm_backends",
}

_PLACEHOLDER = re.compile(r"<[^>]+>")

# classification values
SAFE = "safe"
GATED = "gated"
NEEDS_ARGS = "needs_args"

Runner = Callable[[str, str, int], "tuple[int, str]"]


def _runnable(command: str) -> bool:
    """A command is runnable only if it's a concrete invocation, not a pointer.

    The conductor falls back to ``see skills/<name>/SKILL.md`` for capabilities
    with no concrete command — those can't be launched.
    """
    return bool(command.strip()) and not command.strip().lower().startswith("see ")


def classify(step: dict) -> str:
    """Decide whether a plan step may run unattended."""
    command = step.get("command", "")
    if _PLACEHOLDER.search(command) or not _runnable(command):
        return NEEDS_ARGS
    if not step.get("local", True):
        return GATED  # escalates to the cloud — never silent
    if step.get("capability") in SAFE_CAPS:
        return SAFE
    return GATED  # unknown / mutating — gate by default


def _tail(text: str, n: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else "…" + text[-n:]


def _default_runner(command: str, cwd: str, timeout: int) -> "tuple[int, str]":
    """Run a command, returning (exit_code, combined_output)."""
    parts = [p.strip('"') for p in shlex.split(command, posix=False)]
    if parts and parts[0] == "python":
        parts[0] = sys.executable  # use the interpreter that's actually running
    try:
        proc = subprocess.run(
            parts, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, f"timeout after {timeout}s"
    except (FileNotFoundError, OSError) as exc:
        return -1, f"could not launch: {exc}"


@dataclass
class StepResult:
    order: int
    capability: str
    command: str
    classification: str
    status: str  # "ran" | "skipped" | "blocked" | "failed"
    exit_code: Optional[int]
    duration_s: float
    note: str
    why: str

    def to_dict(self) -> dict:
        return asdict(self)


def execute(plan_dict: dict, *, confirm: bool = False, dry_run: bool = False,
            timeout: int = 120, cwd: str = ".",
            runner: Optional[Runner] = None) -> dict:
    """Run the runnable steps of a plan; classify and report on the rest.

    Returns a report dict: goal, mode, summary counts, and per-step results.
    """
    if "error" in plan_dict:
        return {"error": plan_dict["error"]}
    steps = plan_dict.get("steps", [])
    if not steps:
        return {"error": "plan has no steps"}

    run = runner or _default_runner
    results: list[dict] = []
    counts = {"ran": 0, "skipped": 0, "blocked": 0, "failed": 0}

    for s in steps:
        cls = classify(s)
        order = s.get("order")
        cap = s.get("capability", "")
        cmd = s.get("command", "")
        why = s.get("why", "")

        will_run = not dry_run and (cls == SAFE or (cls == GATED and confirm))

        if not will_run:
            if dry_run:
                status, note = "skipped", f"dry-run: classified {cls}"
            elif cls == NEEDS_ARGS:
                note = ("command needs arguments (fill the <placeholder>)"
                        if _PLACEHOLDER.search(cmd)
                        else "no concrete command (see the capability's SKILL.md)")
                status = "skipped"
            elif cls == GATED:
                status, note = "blocked", "gated — re-run with confirm=true to execute"
            else:  # pragma: no cover - defensive
                status, note = "skipped", cls
            results.append(StepResult(order, cap, cmd, cls, status, None, 0.0,
                                      note, why).to_dict())
            counts[status] += 1
            continue

        t0 = time.time()
        code, out = run(cmd, cwd, timeout)
        dt = round(time.time() - t0, 2)
        status = "ran" if code == 0 else "failed"
        results.append(StepResult(order, cap, cmd, cls, status, code, dt,
                                  _tail(out), why).to_dict())
        counts[status] += 1

    return {
        "goal": plan_dict.get("goal", ""),
        "mode": "dry_run" if dry_run else ("confirmed" if confirm else "safe_only"),
        "summary": counts,
        "cloud_tokens": 0,
        "results": results,
    }


def run_goal(goal: str, *, confirm: bool = False, dry_run: bool = False,
             timeout: int = 120, cwd: str = ".", top_k: int = 6,
             runner: Optional[Runner] = None) -> dict:
    """Plan a goal, then execute its runnable steps. Convenience wrapper."""
    from skills.conductor.conductor import plan as _plan
    p = _plan(goal, top_k=top_k)
    if "error" in p:
        return p
    return execute(p, confirm=confirm, dry_run=dry_run, timeout=timeout,
                   cwd=cwd, runner=runner)
