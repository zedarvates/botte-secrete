"""Explicit skill plans with local evidence, dependency checks and checkpoints.

The caller supplies a trusted plan and current task authority. File predicates
verify only the stated conditions, never the complete effects of a subprocess.
This opt-in executor does not interpret effects declarations as executable code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath

from skills.atomic_json import write_json
from skills.conductor.conductor import CAP_COMMAND
from skills.conductor.executor import GATED, NEEDS_ARGS, SAFE, _default_runner, classify

PLAN_SCHEMA = "botte.skill-plan/v1"
RUN_SCHEMA = "botte.skill-run/v1"
MAX_DOCUMENT = 1024 * 1024
MAX_REPORT = 32 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
STATES = {"pending", "running", "verified", "unverified", "failed", "blocked",
          "skipped", "uncertain", "stale"}
CHECKS = {"file_exists", "file_absent", "file_sha256", "text_contains", "json_equals"}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _keys(value, required, optional=()) -> None:
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise ValueError("missing required object fields")
    if value.keys() - set(required) - set(optional):
        raise ValueError("unknown object fields")


def _text(value) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        raise ValueError("expected a nonempty bounded string")


def _path(value) -> None:
    _text(value)
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (posix.is_absolute() or windows.drive or "\\" in value or "\x00" in value
            or ":" in value or ".." in posix.parts or value == "."):
        raise ValueError("paths must be relative to the selected project")


def _array(value, limit=100) -> None:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("expected a bounded array")


def validate_plan(plan: dict) -> None:
    """Validate the entire plan before any subprocess or checkpoint write."""
    _keys(plan, ("schema", "goal", "context", "steps"))
    if plan["schema"] != PLAN_SCHEMA:
        raise ValueError("unsupported skill plan schema")
    _text(plan["goal"])
    _text(plan["context"])
    _array(plan["steps"])
    if not plan["steps"]:
        raise ValueError("plan has no steps")
    if len(json.dumps(plan, allow_nan=False).encode()) > MAX_DOCUMENT:
        raise ValueError("plan exceeds size limit")
    seen = set()
    for step in plan["steps"]:
        _keys(step, ("id", "capability", "command", "local", "needs", "requires",
                     "ensures", "observes", "source_hashes"), ("effects_before",))
        for key in ("id", "capability", "command"):
            _text(step[key])
        if step["id"] in seen or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", step["id"]):
            raise ValueError("step IDs must be unique simple identifiers")
        if type(step["local"]) is not bool:
            raise ValueError("local must be a boolean")
        _array(step["needs"])
        for dependency in step["needs"]:
            _text(dependency)
            if dependency not in seen:
                raise ValueError("dependencies must refer to earlier steps")
        if len(set(step["needs"])) != len(step["needs"]):
            raise ValueError("duplicate dependency")
        seen.add(step["id"])
        _array(step["observes"])
        for path in step["observes"]:
            _path(path)
        if not isinstance(step["source_hashes"], dict) or len(step["source_hashes"]) > 100:
            raise ValueError("invalid source bindings")
        for path, digest in step["source_hashes"].items():
            _path(path)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("source binding needs a SHA-256 digest")
        for key in ("requires", "ensures"):
            _array(step[key])
            for check in step[key]:
                _keys(check, ("kind", "path"), ("value", "pointer"))
                if check["kind"] not in CHECKS:
                    raise ValueError("unsupported local check")
                _path(check["path"])
                kind = check["kind"]
                if kind in {"file_exists", "file_absent"}:
                    _keys(check, ("kind", "path"))
                elif kind in {"file_sha256", "text_contains"}:
                    _keys(check, ("kind", "path", "value"))
                    _text(check["value"])
                    if kind == "file_sha256" and not re.fullmatch(r"[0-9a-f]{64}", check["value"]):
                        raise ValueError("file_sha256 needs a SHA-256 digest")
                else:
                    _keys(check, ("kind", "path", "pointer", "value"))
                    pointer = check["pointer"]
                    if (not isinstance(pointer, str) or len(pointer) > 1024
                            or (pointer and not pointer.startswith("/"))
                            or re.search(r"~(?![01])", pointer)):
                        raise ValueError("invalid JSON pointer")


def _resolve(root: Path, path: str) -> Path:
    _path(path)
    target = root / path
    # Reject symlinks including dangling ones, before resolving their targets.
    cursor = root
    for part in PurePosixPath(path).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("symlink observation paths are not supported")
    target.resolve().relative_to(root)
    return target


def _read(root: Path, path: str) -> tuple[dict, bytes | None]:
    try:
        target = _resolve(root, path)
        if not target.exists():
            return {"state": "absent"}, None
        if not target.is_file():
            return {"state": "unknown", "reason": "not a regular file"}, None
        with target.open("rb") as stream:
            data = stream.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            return {"state": "unknown", "reason": "file exceeds observation limit"}, None
        return {"state": "file", "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest()}, data
    except (OSError, ValueError):
        return {"state": "unknown", "reason": "file unavailable or outside scope"}, None


def _check(root: Path, checks: list) -> list[dict]:
    results = []
    for check in checks:
        observed, data = _read(root, check["path"])
        kind = check["kind"]
        passed = False
        if observed["state"] != "unknown":
            if kind == "file_absent":
                passed = observed["state"] == "absent"
            elif kind == "file_exists":
                passed = data is not None
            elif data is not None:
                try:
                    if kind == "file_sha256":
                        passed = observed["sha256"] == check["value"]
                    elif kind == "text_contains":
                        passed = check["value"] in data.decode("utf-8")
                    else:
                        value = json.loads(data.decode("utf-8"))
                        if check["pointer"]:
                            for part in check["pointer"][1:].split("/"):
                                part = part.replace("~1", "/").replace("~0", "~")
                                if isinstance(value, list):
                                    if not re.fullmatch(r"0|[1-9][0-9]*", part):
                                        raise ValueError("invalid array index")
                                    value = value[int(part)]
                                else:
                                    value = value[part]
                        passed = _digest(value) == _digest(check["value"])
                except (ValueError, UnicodeError, TypeError, KeyError, IndexError):
                    passed = False
        results.append({"kind": kind, "path": check["path"], "passed": passed,
                        "observed": observed})
    return results


def _passed(checks: list) -> bool:
    return all(check["passed"] for check in checks)


def _sources(root: Path, step: dict) -> list:
    return _check(root, [{"kind": "file_sha256", "path": path, "value": digest}
                         for path, digest in step["source_hashes"].items()])


def _observations(root: Path, step: dict) -> dict:
    paths = set(step["observes"]) | {c["path"] for c in step["ensures"]}
    return {p: _read(root, p)[0] for p in sorted(paths)}


def _classification(step: dict) -> str:
    result = classify(step)
    # A caller's capability label must not make an arbitrary command unattended.
    if result == SAFE and step["command"] != CAP_COMMAND.get(step["capability"]):
        return GATED
    return result


def read_document(path: str | Path, *, limit: int = MAX_DOCUMENT) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("document exceeds size limit")
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


@contextmanager
def _checkpoint_lock(target: Path | None):
    if target is None:
        yield
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(target.name + ".lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def execute_verified(plan: dict, *, cwd: str = ".", confirm: bool = False,
                     dry_run: bool = False, timeout: int = 120,
                     checkpoint: str | None = None, resume: bool = False,
                     runner=None) -> dict:
    """Execute a trusted explicit plan; use an exclusive checkpoint to resume.

    Resume rechecks verified outputs and starts only previously unstarted steps.
    Started but unresolved work requires reconciliation outside this executor.
    """
    try:
        validate_plan(plan)
        for flag in (confirm, dry_run, resume):
            if type(flag) is not bool:
                raise ValueError("execution flags must be booleans")
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError("timeout must be an integer between 1 and 3600")
        if resume and (checkpoint is None or dry_run):
            raise ValueError("resume requires a checkpoint and an executing run")
        root = Path(cwd).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("project must be a directory")
        target = _resolve(root, checkpoint) if checkpoint is not None else None
        if target:
            used = {p for s in plan["steps"] for p in
                    [*s["observes"], *s["source_hashes"],
                     *(c["path"] for c in s["requires"] + s["ensures"])]}
            if any(_resolve(root, p) in {target, target.with_name(target.name + ".lock")}
                   for p in used):
                raise ValueError("checkpoint must be separate from observed resources")
        plan = deepcopy(plan)
        context = _digest({"root": str(root), "context": plan["context"],
                           "python": sys.version, "executable": sys.executable})
        fingerprint = _digest(plan)
        with _checkpoint_lock(None if dry_run else target):
            if resume:
                report = read_document(target, limit=MAX_REPORT)
                if (not isinstance(report, dict) or report.get("schema") != RUN_SCHEMA
                        or report.get("plan_sha256") != fingerprint
                        or report.get("context_sha256") != context):
                    raise ValueError("checkpoint plan, context or schema does not match")
                rows = report.get("results", [])
                if (not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows)
                        or [r.get("id") for r in rows] != [s["id"] for s in plan["steps"]]
                        or any(r.get("status") not in STATES
                               or type(r.get("started")) is not bool
                               or (r.get("status") == "verified" and
                                   (r.get("exit_code") != 0 or not r.get("started"))) for r in rows)):
                    raise ValueError("invalid checkpoint steps")
            else:
                if target and target.exists() and not dry_run:
                    raise ValueError("checkpoint exists; select resume or a new path")
                report = {"schema": RUN_SCHEMA, "run_id": uuid.uuid4().hex,
                          "plan_sha256": fingerprint, "context_sha256": context,
                          "goal": plan["goal"], "context": plan["context"],
                          "started_at": time.time(), "results": [
                              {"id": s["id"], "capability": s["capability"],
                               "status": "pending", "started": False,
                               "classification": _classification(s), "exit_code": None,
                               "duration_s": 0.0, "reused": False,
                               "effects_before": deepcopy(s.get("effects_before"))}
                              for s in plan["steps"]]}
            return _execute(plan, report, root, confirm, dry_run, timeout,
                            None if dry_run else target, resume, runner or _default_runner)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        return {"error": str(exc)}


def _execute(plan, report, root, confirm, dry_run, timeout, target, resume, run):
    rows = {r["id"]: r for r in report["results"]}
    steps = {s["id"]: s for s in plan["steps"]}

    def check_dependencies(step, row):
        checks, unavailable = {}, []
        for dependency in step["needs"]:
            previous, prior_step = rows[dependency], steps[dependency]
            evidence = {"status": previous["status"],
                        "precondition_checks": _check(root, prior_step["requires"]),
                        "postcondition_checks": _check(root, prior_step["ensures"]),
                        "source_checks": _sources(root, prior_step)}
            checks[dependency] = evidence
            if (evidence["status"] != "verified" or not evidence["postcondition_checks"]
                    or not all(_passed(evidence[key]) for key in
                               ("precondition_checks", "postcondition_checks", "source_checks"))):
                unavailable.append(dependency)
        row["dependency_checks"] = checks
        return unavailable

    def save():
        report["updated_at"] = time.time()
        report["mode"] = "dry_run" if dry_run else "execution"
        report["summary"] = {state: sum(r["status"] == state for r in rows.values())
                             for state in sorted(STATES)}
        report["complete"] = all(r["status"] == "verified" for r in rows.values())
        report["coverage"] = "declared local file checks only; other effects are unobserved"
        report["child_cost"] = None
        if target:
            _resolve(root, target.relative_to(root).as_posix())
            write_json(target, report)

    for step in plan["steps"]:
        row = rows[step["id"]]
        if dry_run:
            row.update(status="skipped", note="preview; no checks or commands executed")
            continue
        if resume and row["started"]:
            # A running checkpoint can mean a still-active child. Never replay it.
            row["reused"] = False
            if row["status"] == "verified":
                evidence = _check(root, step["ensures"])
                source = _sources(root, step)
                required = _check(root, step["requires"])
                row["resume_checks"] = evidence
                row["resume_sources"] = source
                row["resume_precondition_checks"] = required
                dependencies_valid = not check_dependencies(step, row)
                if (evidence and _passed(evidence) and _passed(source)
                        and _passed(required) and dependencies_valid):
                    row.update(reused=True, note="verified outputs rechecked; command not repeated")
                else:
                    row.update(status="stale", note="previous evidence changed; reconcile before retry")
            else:
                row.update(status="uncertain", note="started work needs reconciliation; command not repeated")
            save()
            continue

        row["classification"] = _classification(step)
        if row["classification"] == NEEDS_ARGS:
            row.update(status="skipped", note="command needs concrete arguments")
            save()
            continue
        if row["classification"] == GATED and not confirm:
            row.update(status="blocked", note="command requires existing task authority and confirm=true")
            save()
            continue
        row.pop("dependencies", None)
        unavailable = check_dependencies(step, row)
        if unavailable:
            row.update(status="blocked", note="dependencies not currently verified", dependencies=unavailable)
            save()
            continue
        source = _sources(root, step)
        required = _check(root, step["requires"])
        row.update(source_checks=source, precondition_checks=required)
        if not _passed(source) or not _passed(required):
            row.update(status="blocked", note="source binding or precondition not satisfied")
            save()
            continue

        before = _observations(root, step)
        row.update(status="running", started=True, before=before, note="command started")
        save()  # Persist before dispatch; losing the process cannot silently repeat a write.
        started = time.monotonic()
        interrupted = None
        try:
            code, output = run(step["command"], str(root), timeout)
            if type(code) is not int or not isinstance(output, str):
                raise ValueError("runner must return an integer and text")
        except BaseException as exc:
            code, output = -1, type(exc).__name__
            if not isinstance(exc, Exception):
                interrupted = exc
        after = _observations(root, step)
        evidence = _check(root, step["ensures"])
        sources_after = _sources(root, step)
        status = ("uncertain" if code == -1 else "failed" if code != 0
                  else "verified" if evidence and _passed(evidence) and _passed(sources_after)
                  else "unverified")
        row.update(status=status, exit_code=code, duration_s=round(time.monotonic() - started, 6),
                   after=after, postcondition_checks=evidence,
                   source_checks_after=sources_after,
                   source_coverage="listed files only" if source else "unbound",
                   changed_paths=[p for p in before if before[p] != after[p]],
                   output_sha256=hashlib.sha256(output.encode("utf-8")).hexdigest(),
                   output_bytes=len(output.encode("utf-8")),
                   note="declared checks passed" if status == "verified" else
                        "execution or evidence incomplete; inspect state before retry")
        save()
        if interrupted:
            raise interrupted
    save()
    return report
