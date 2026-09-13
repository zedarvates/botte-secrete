"""Read retained observations by ID; never follow recorded resource references."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from copy import deepcopy
from pathlib import Path, PurePosixPath

from skills.capabilities.effects import _unique_object
from skills.capabilities.observations import MAX_REPORT_BYTES, summarize, validate_report

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_GROUPS = {"calls": "status", "observations": "comparison", "network": "status"}


def _request(selectors, expected_sha256):
    if expected_sha256 is not None and (not isinstance(expected_sha256, str)
                                        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 hex digest")
    if selectors is None:
        return None
    if not isinstance(selectors, list) or not 1 <= len(selectors) <= 16:
        raise ValueError("selectors must be a list of 1 to 16 explicit record paths")
    parsed = {}
    for selector in selectors:
        if not isinstance(selector, str) or len(selector) > 16416:
            raise ValueError("invalid evidence selector")
        parts = selector.split("/")
        if (len(parts) != 3 or parts[0] or parts[1] not in {*_GROUPS, "declarations"}
                or not parts[2] or re.search(r"~(?![01])", parts[2])):
            raise ValueError("select /calls/ID, /observations/ID, /network/ID or /declarations/DIGEST")
        identity = parts[2].replace("~1", "/").replace("~0", "~")
        if len(identity) > 8192 or (parts[1] == "declarations"
                                   and not re.fullmatch(r"[0-9a-f]{64}", identity)):
            raise ValueError("invalid evidence record ID")
        parsed[selector] = (parts[1], identity)
    return parsed


def _unavailable(reason):
    return {"selection_status": "unavailable", "reason": reason,
            "evidence_sha256": None, "matches_expected": None, "selected": {}}


def _project(report, parsed, expected_sha256):
    try:
        raw = json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_REPORT_BYTES:
            return _unavailable("evidence_too_large")
        errors = validate_report(report)
    except (ValueError, TypeError, RecursionError):
        return _unavailable("invalid_evidence")
    if errors:
        return {**_unavailable("invalid_evidence"), "error_count": len(errors)}
    actual = hashlib.sha256(raw).hexdigest()
    matches = actual == expected_sha256 if expected_sha256 is not None else None
    result = {"selection_status": "changed" if matches is False else "indexed",
              "observation_schema": report["schema"], "run_id": report["run_id"],
              "evidence_sha256": actual, "matches_expected": matches, "selected": {}}
    if matches is False:
        return result
    records = {group: {r["id"]: r for r in report.get(group, [])} for group in _GROUPS}
    records["declarations"] = report["declarations"]
    if parsed is not None:
        missing = [s for s, (group, identity) in parsed.items() if identity not in records[group]]
        if missing:
            return {**result, "selection_status": "not_found", "missing_selectors": missing}
        selected = {s: records[group][identity] for s, (group, identity) in parsed.items()}
        linked = {}
        for selector, (group, identity) in parsed.items():
            record = selected[selector]
            call_id = (record["parent_id"] if group == "calls" else
                       record["call_id"] if group in {"observations", "network"} else None)
            while call_id is not None and call_id not in linked:
                call = records["calls"][call_id]
                if ("calls", call_id) not in parsed.values():
                    linked[call_id] = call
                # validate_report requires every parent to precede its child.
                call_id = call["parent_id"]
        result.update(selection_status="selected", selected=selected, linked_calls=linked)
    else:
        index = {}
        for group, field in _GROUPS.items():
            if group not in report:  # v1 has no network collection.
                continue
            index[group] = {}
            for record in report[group]:
                index[group].setdefault(record[field], []).append(record["id"])
        index["declarations"] = list(report["declarations"])
        result["index"] = index
    result.update(context=report["context"], process=report["process"],
                  problems=report["problems"], limitations=report["limitations"],
                  summary=summarize(report), task_outcome="unverified")
    return deepcopy(result)


def select_evidence(report: object, selectors: list[str] | None = None, *,
                    expected_sha256: str | None = None) -> dict:
    """Project one complete v1/v2 companion supplied by the caller, without I/O.

    Omit selectors for an ID index grouped by recorded status/comparison. Detail
    reads preserve entire records and their ancestor calls, plus run-wide limits.
    The digest binds this companion, not its author or current resource state.
    """
    return _project(report, _request(selectors, expected_sha256), expected_sha256)


def _read_document(path):
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("expected bounded regular report file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise ValueError("report changed while opening")
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        after = os.fstat(stream.fileno())
    if (len(raw) > MAX_DOCUMENT_BYTES or identity(opened) != identity(after)
            or identity(after) != identity(path.lstat())):
        raise ValueError("report changed while reading or exceeds size limit")
    def reject_constant(_):
        raise ValueError("non-finite JSON number")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=reject_constant)


def read_evidence(path: Path, selectors: list[str] | None = None, *,
                  result_index: int | None = None, expected_sha256: str | None = None) -> dict:
    """Read a standalone companion or an explicitly indexed saved execution step.

    The document is bounded to 16 MiB, the selected canonical companion to 2 MiB.
    Other execution fields and all embedded paths are ignored, never followed.
    """
    parsed = _request(selectors, expected_sha256)
    if result_index is not None and (type(result_index) is not int or result_index < 0):
        raise ValueError("result_index must be a non-negative integer")
    try:
        document = _read_document(Path(path))
    except (OSError, ValueError, TypeError, RecursionError, RuntimeError):
        return _unavailable("unreadable_document")
    report = document
    if result_index is not None:
        results = document.get("results") if isinstance(document, dict) else None
        if (not isinstance(results, list) or result_index >= len(results)
                or not isinstance(results[result_index], dict)):
            return _unavailable("result_not_found")
        report = results[result_index].get("effects_observed")
        if report is None:
            return _unavailable("not_observed")
    elif isinstance(document, dict) and "results" in document:
        return _unavailable("result_index_required")
    result = _project(report, parsed, expected_sha256)
    result.update(source=str(path), result_index=result_index)
    return result


def read_saved_evidence(source: str, selectors: list[str] | None = None, *,
                        result_index: int | None = None, expected_sha256: str | None = None) -> dict:
    """MCP entry: canonical .botte/reports/<file>.json in the server working tree."""
    if not isinstance(source, str) or not source or "\\" in source or ":" in source:
        raise ValueError("source must be a canonical .botte/reports/<file>.json path")
    relative = PurePosixPath(source)
    if (relative.parts[:2] != (".botte", "reports") or len(relative.parts) != 3
            or relative.suffix != ".json" or relative.as_posix() != source):
        raise ValueError("source must be a canonical .botte/reports/<file>.json path")
    path = Path.cwd().resolve().joinpath(*relative.parts)
    try:
        if path.resolve() != path:
            raise ValueError("report aliases are unsupported; use a canonical saved report")
    except (OSError, RuntimeError) as exc:
        raise ValueError("report source cannot be resolved") from exc
    result = read_evidence(path, selectors, result_index=result_index, expected_sha256=expected_sha256)
    result["source"] = source
    return result
