"""Opt-in, cooperative effect evidence. No tracing or authority by default.

Only instrumented calls, writes and network attempts are observed. Samples and
transport responses do not prove causality, absence of other effects, or success.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import platform
import re
import stat
import time
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from threading import RLock
from uuid import uuid4

from skills.capabilities.effects import inspect_effects, validate_contract

SCHEMA = "botte.effect-observations/v2"
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_CALLS = 128
MAX_OBSERVATIONS = 256
_SESSION = ContextVar("botte_effect_session", default=None)
_CALL = ContextVar("botte_effect_call", default=None)

LIMITATIONS = [
    "Cooperative instrumentation covers selected calls, writes and network attempts only.",
    "Transport responses do not verify remote effects, model costs or task success.",
    "Only explicitly propagated worker contexts share a session; no OS-wide tracing.",
    "File samples do not exclude concurrent writers, transient changes or other effects.",
    "A supported write facet does not validate the whole declared effect or its conditions.",
    "Reports are local evidence, not authenticated attestations or permission to retry.",
]


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def empty_report(run_id: str | None = None) -> dict:
    return {"schema": SCHEMA, "run_id": run_id or uuid4().hex,
            "context": {"started_at": datetime.now(timezone.utc).isoformat(),
                        "cwd": str(Path.cwd()), "python": platform.python_version()},
            "process": {"status": "running", "exit_code": None},
            "calls": [], "declarations": {}, "observations": [], "network": [],
            "problems": [], "limitations": list(LIMITATIONS)}


def file_state(path: Path) -> dict:
    """Bounded regular-file sampling; never read contents into the report."""
    unknown = {"state": "unknown", "sha256": None, "size": None}
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            return unknown
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                return unknown
            raw = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        def identity(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
        if (len(raw) > MAX_FILE_BYTES or identity(before) != identity(opened)
                or identity(opened) != identity(after)
                or identity(after) != identity(path.lstat())):
            return unknown
        return {"state": "present", "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw)}
    except FileNotFoundError:
        # A disappearance after the initial stat is an uncertain sample.
        return unknown if "before" in locals() else {
            "state": "missing", "sha256": None, "size": None}
    except (OSError, ValueError):
        return unknown


def reconcile(observation: dict, declaration_status: str) -> str:
    """Compare only the instrumented 'file present after write' facet."""
    if declaration_status != "declared" or observation["effect_ref"] is None:
        return "unknown"
    if observation["write_status"] == "raised":
        return "deviation"
    if observation["write_status"] != "returned" or observation["after"]["state"] == "unknown":
        return "unknown"
    return "supported" if observation["after"]["state"] == "present" else "deviation"


def _locked(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return function(self, *args, **kwargs)
    return wrapped


def submit_observed(pool, function, *args):
    """Propagate only explicitly enrolled worker calls; preserve normal results."""
    if _SESSION.get() is None:
        return pool.submit(function, *args)
    return pool.submit(copy_context().run, function, *args)


class ObservationSession:
    """Collect in memory, optionally checkpointing to a caller-owned private file."""

    def __init__(self, *, run_id: str | None = None, checkpoint: Path | None = None):
        self.report = empty_report(run_id)
        self.checkpoint = checkpoint
        self._lock = RLock()
        self._targets = {}  # Run-local aliases; actual origins never enter reports.
        self._closed = False

    @_locked
    def problem(self, message: str) -> None:
        if message not in self.report["problems"]:
            self.report["problems"].append(message)

    @_locked
    def flush(self) -> None:
        if self._closed or self.checkpoint is None:
            return
        try:
            if len(json.dumps(self.report).encode("utf-8")) > MAX_REPORT_BYTES:
                self.problem("checkpoint size limit reached; persisted evidence may be incomplete")
                return
            from skills.atomic_json import write_json
            write_json(self.checkpoint, self.report, indent=None)
        except (OSError, ValueError):
            self.problem("checkpoint unavailable; persisted evidence may be incomplete")

    def __enter__(self):
        if self._closed:
            raise ValueError("observation sessions cannot be reopened")
        self._token = _SESSION.set(self)
        self._parent_token = _CALL.set(None)
        self.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        _CALL.reset(self._parent_token)
        _SESSION.reset(self._token)
        with self._lock:
            if any(c["status"] == "running" for c in self.report["calls"]):
                self.problem("session closed with unfinished calls; later effects are unobserved")
            self.flush()
            self._closed = True
            self.report = deepcopy(self.report)  # Detach records held by late workers.
            self._targets.clear()

    @_locked
    def _begin_call(self, skill_dir: Path, operation: str, context: dict | None):
        if self._closed:
            return None
        if len(self.report["calls"]) >= MAX_CALLS:
            self.problem("call limit reached; nested observations omitted")
            return None
        snapshot = inspect_effects(skill_dir)
        contract = snapshot.get("contract")
        ref = digest(contract) if contract else None
        if ref:
            self.report["declarations"][ref] = deepcopy(contract)
        call = {"id": f"c{len(self.report['calls']) + 1}", "parent_id": _CALL.get(),
                "capability_id": contract["capability_id"] if contract else None,
                "source_path": str(Path(skill_dir).resolve()),
                "operation": operation, "context": context or {}, "status": "running",
                "duration_ms": None, "declaration_status": snapshot["status"],
                "declaration_ref": ref}
        self.report["calls"].append(call)
        self.flush()
        return call

    @contextmanager
    def call(self, skill_dir: Path, operation: str, context: dict | None = None):
        call = self._begin_call(skill_dir, operation, context)
        token = _CALL.set(call["id"] if call else None)
        start = time.monotonic()
        status = "returned"
        try:
            yield
        except BaseException:
            status = "raised"
            raise
        finally:
            _CALL.reset(token)
            if call:
                with self._lock:
                    call["status"] = status
                    call["duration_ms"] = max(0, round((time.monotonic() - start) * 1000))
                    self.flush()


def observed_operation(operation: str):
    """Decorate a synchronous skill function; inactive calls do no extra I/O."""
    def decorate(function):
        skill_dir = Path(function.__code__.co_filename).resolve().parent

        @wraps(function)
        def wrapped(*args, **kwargs):
            session = _SESSION.get()
            if session is None:
                return function(*args, **kwargs)
            bound = inspect.signature(function).bind(*args, **kwargs)
            bound.apply_defaults()
            # Record only explicit boolean controls, not tasks, keys or endpoints.
            context = {k: v for k, v in bound.arguments.items()
                       if k in {"fresh", "scan_subnet"} and isinstance(v, bool)}
            with session.call(skill_dir, operation, context):
                return function(*args, **kwargs)
        return wrapped
    return decorate


@contextmanager
def observed_file_write(path: Path, effect_ref: str):
    """Instrument an existing write, including partial changes before an error.

    The reference identifies an effect in this call's immutable declaration.
    It must be authored in reviewed code, never taken from a task or sidecar.
    """
    session = _SESSION.get()
    call_id = _CALL.get()
    if session is None or call_id is None or session._closed:
        yield
        return
    with session._lock:
        if session._closed:
            observation = None
        elif len(session.report["observations"]) >= MAX_OBSERVATIONS:
            session.problem("observation limit reached; further writes unassessed")
            observation = None
        else:
            call = next(c for c in session.report["calls"] if c["id"] == call_id)
            contract = session.report["declarations"].get(call["declaration_ref"], {})
            matched = re.fullmatch(r"/(expected_effects|downstream_effects)/([0-9]+)", effect_ref)
            if matched is None or int(matched[2]) >= len(contract.get(matched[1], [])):
                effect_ref = None
            observation = {"id": f"o{len(session.report['observations']) + 1}", "call_id": call_id,
                           "resource": str(Path(path).absolute()), "effect_ref": effect_ref,
                           "facet": "file_present_after_write", "write_status": "running",
                           "before": file_state(Path(path)),
                           "after": {"state": "unknown", "sha256": None, "size": None},
                           "comparison": "unknown"}
            session.report["observations"].append(observation)
        session.flush()
    if observation is None:
        yield
        return
    status = "returned"
    try:
        yield
    except BaseException:
        status = "raised"
        raise
    finally:
        after = file_state(Path(path))
        with session._lock:
            observation["write_status"] = status
            observation["after"] = after
            observation["comparison"] = reconcile(observation, call["declaration_status"])
            session.flush()


def summarize(report: dict) -> dict:
    """Keep incomplete/failed descendants visible even if their parent returned."""
    network = report.get("network", [])
    interrupted = (any(n["method"] == "POST" and n["status"] != "returned" for n in network)
                   or report["process"]["status"] in {"timed_out", "launch_failed", "runner_error"}
                   or report["process"]["exit_code"] not in (None, 0)
                   or any(c["status"] != "returned" for c in report["calls"])
                   or any(o["write_status"] != "returned" or o["comparison"] == "deviation"
                          for o in report["observations"]))
    return {"calls": len(report["calls"]),
            "network_attempts": len(network),
            "network_failures": sum(n["status"] == "raised" for n in network),
            "unfinished_network": sum(n["status"] == "running" for n in network),
            "http_responses": sum(n["http_status"] is not None for n in network),
            "unfinished_calls": sum(c["status"] == "running" for c in report["calls"]),
            "raised_calls": sum(c["status"] == "raised" for c in report["calls"]),
            "failed_writes": sum(o["write_status"] == "raised" for o in report["observations"]),
            "supported_write_facets": sum(o["comparison"] == "supported" for o in report["observations"]),
            "deviations": sum(o["comparison"] == "deviation" for o in report["observations"]),
            "unknown_write_facets": sum(o["comparison"] == "unknown" for o in report["observations"]),
            "unassessed_effects": sum(len(d["expected_effects"]) + len(d["downstream_effects"])
                                      for d in report["declarations"].values()),
            "next_action": ("no_execution_evidence" if report["process"]["status"] == "not_run" else
                            "inspect_partial_state_before_retry" if interrupted else
                            "review_unassessed_effects_before_reuse")}


def validate_report(report: object) -> list[str]:
    """Validate transport structure, fingerprints and graph references, stdlib-only."""
    from skills.capabilities.observation_schema import REPORT_SCHEMA, REPORT_SCHEMA_V2, validate_shape
    schema = (REPORT_SCHEMA_V2 if isinstance(report, dict) and report.get("schema") == SCHEMA
              else REPORT_SCHEMA)
    errors = validate_shape(report, schema)
    if errors:
        return errors
    declarations = report["declarations"]
    for ref, contract in declarations.items():
        if digest(contract) != ref or validate_contract(contract):
            errors.append("invalid declaration binding")
    if errors:
        return errors
    calls = {}
    for call in report["calls"]:
        if call["id"] in calls or (call["parent_id"] is not None and call["parent_id"] not in calls):
            errors.append("duplicate call or parent not recorded before child")
        calls[call["id"]] = call
        ref = call["declaration_ref"]
        contract = declarations.get(ref)
        if ((call["declaration_status"] in {"declared", "stale"}) != (contract is not None)
                or (contract is None and (ref is not None or call["capability_id"] is not None))
                or (contract is not None and contract["capability_id"] != call["capability_id"])):
            errors.append("invalid call declaration reference")
    seen = set()
    for observation in report["observations"]:
        if observation["id"] in seen or observation["call_id"] not in calls:
            errors.append("duplicate observation or missing call")
            continue
        seen.add(observation["id"])
        call = calls[observation["call_id"]]
        ref = observation["effect_ref"]
        if ref is not None:
            group, index = ref.strip("/").split("/")
            contract = declarations.get(call["declaration_ref"], {})
            if int(index) >= len(contract.get(group, [])):
                errors.append("effect reference outside declaration")
        for state in (observation["before"], observation["after"]):
            if (state["state"] == "present") != (state["sha256"] is not None and state["size"] is not None):
                errors.append("invalid file sample")
            if state["state"] != "present" and (state["sha256"] is not None or state["size"] is not None):
                errors.append("unknown or missing sample must not carry file evidence")
        if observation["comparison"] != reconcile(observation, call["declaration_status"]):
            errors.append("comparison disagrees with recorded evidence")
    if report.get("network"):
        from skills.capabilities.network_observations import compare_network
        seen = set()
        targets = {}
        for record in report["network"]:
            if record["id"] in seen or record["call_id"] not in calls:
                errors.append("duplicate network observation or missing call")
                continue
            seen.add(record["id"])
            call = calls[record["call_id"]]
            ref = record["effect_ref"]
            if ref is not None:
                group, index = ref.strip("/").split("/")
                contract = declarations.get(call["declaration_ref"], {})
                if int(index) >= len(contract.get(group, [])):
                    errors.append("network effect reference outside declaration")
            if record["comparison"] != compare_network(record, call["declaration_status"]):
                errors.append("network comparison disagrees with recorded evidence")
            if (record["status"] == "raised") != (record["error_kind"] is not None):
                errors.append("network error disagrees with attempt status")
            if (record["status"] == "running") != (record["duration_ms"] is None):
                errors.append("network duration disagrees with attempt status")
            if record["transport"] == "tcp":
                if record["method"] != "CONNECT" or record["target"]["scheme"] != "tcp" or any(
                        record[k] is not None for k in ("http_status", "response_target",
                                                       "origin_changed", "response_complete")):
                    errors.append("TCP observation contains HTTP evidence")
            elif (record["method"] == "CONNECT" or record["target"]["scheme"] == "tcp"
                  or record["response_complete"] is None
                  or (record["response_target"] is not None
                      and record["response_target"]["scheme"] == "tcp")):
                errors.append("HTTP observation has invalid transport fields")
            for target in (record["target"], record["response_target"]):
                if target is not None:
                    if target["id"] in targets and targets[target["id"]] != target:
                        errors.append("inconsistent target alias")
                    targets[target["id"]] = target
            response = record["response_target"]
            changed = (response != record["target"] if response is not None and
                       response["scheme"] != "unknown" and record["target"]["scheme"] != "unknown"
                       else None)
            if record["origin_changed"] != changed:
                errors.append("origin change disagrees with target evidence")
    return errors
