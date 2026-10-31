"""Versioned verification receipts proposed to the existing Memory Hub.

Preparation is a bounded transformation, without filesystem/network/database
access. Reports and documentary links remain caller-supplied, unverified data.
Explicit persistence uses MemoryStore's current v2 quarantine contract; it does
not activate retrieval, promote knowledge or execute remembered content.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
import time
from urllib.parse import urlsplit

from skills.memory_hub.schema import MemoryEntry
from skills.memory_hub.store import MemoryStore


_SCHEMA = "parcimonia.verification-memory-proposal/v1"
_MAX_INPUT = 512 * 1024
_MAX_OUTPUT = 64 * 1024
_MAX_ROWS = 2048
_SELECTED = 12
_AGENT = "parcimonia-verification"
_PROJECT = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9._-]{0,127}\Z")
_SHA = re.compile(r"\A[0-9a-f]{64}\Z")
_SPECS = {
    "parcimonia.reproduction-reduction/v1": (
        "reproduction", "A preserved failure means the bug was reproduced, not fixed.",
        {"reduced", "unchanged", "not_reproduced", "inconclusive"}),
    "parcimonia.flaky-triage/v1": (
        "intermittency", "Classification describes finite attempts; a later pass does not erase a failure.",
        {"reproduced_failure", "intermittent_observed", "varying_failures_observed",
         "no_failure_observed", "environment_unavailable", "insufficient_evidence"}),
    "parcimonia.mutation-checks/v1": (
        "mutation", "Completed means bounded mutants were attempted; survivors/inconclusive results remain findings.",
        {"completed", "incomplete", "baseline_failed", "baseline_inconclusive", "budget_exhausted", "no_mutants"}),
    "parcimonia.interface-exploration/v1": (
        "interface", "Completed is an exhausted observed frontier, not global coverage or GUI qualification.",
        {"completed", "failed", "incomplete"}),
    "parcimonia.conformance/v1": (
        "conformance", "Passing concerns declared projections and retains known differences and uncovered contracts.",
        {"passed", "passed_with_known_differences", "failed", "incomplete", "not_run"}),
    "parcimonia.test-order/v1": (
        "test_order", "This is an ordering proposal, not a test execution or current passing result.", {"proposed"}),
}
_BOUNDARIES = {"execution": False, "network": False, "model_calls": 0,
               "memory_promotion": False, "executable_instruction": False,
               "storage_target": "memory_quarantine", "report_truth": "unverified",
               "document_links": "caller_declared_not_fetched"}
_UNKNOWNS = ["report_authenticity", "source_freshness", "current_target_correctness",
             "general_reliability", "end_to_end_savings"]
_BOUNDARY_FIELDS = {
    "reproduction": {"oracle", "oracle_isolation", "time_limit", "global_minimum", "future_stability"},
    "intermittency": {"cause_diagnosed", "general_reliability_established", "adapter_data_verified", "automatic_repair"},
    "mutation": {"harness_writes_original_files", "security_sandbox", "network_isolation", "mutation_coverage", "callback_deadline"},
    "interface": {"graphical_qualification", "global_reachability_proved", "callback_timeout"},
    "conformance": {"network_requested", "model_calls", "sandbox", "trusted_local_module_execution"},
    "test_order": {"execution", "skips_required_checks", "measured_savings"},
}


def _encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value, name, maximum=512):
    if (not isinstance(value, str) or not value.strip()
            or len(value.encode("utf-8")) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError(f"invalid bounded {name}")
    return value


def _uri(value):
    value = _text(value, "source URI")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https", "file", "urn", "repo", "memory"}
                or parsed.username is not None or parsed.password is not None
                or (parsed.scheme in {"http", "https"} and not parsed.hostname)):
            raise ValueError("unsupported source URI")
        _ = parsed.port
    except ValueError:
        raise ValueError("invalid source URI") from None
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _load(report_json):
    if not isinstance(report_json, str):
        raise ValueError("report_json must be a JSON string")
    raw = report_json.encode("utf-8")
    if not 1 <= len(raw) <= _MAX_INPUT:
        raise ValueError("report exceeds byte limit")
    try:
        report = json.loads(report_json, object_pairs_hook=_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if not isinstance(report, dict) or not isinstance(report.get("schema"), str) or report["schema"] not in _SPECS:
            raise ValueError("unsupported verification report schema")
        _encode(report)
    except (RecursionError, UnicodeError, OverflowError):
        raise ValueError("unsupported JSON structure") from None
    return report, raw


def _small(value, maximum=4096):
    """Keep a selected field or an explicit digest/omission, never silent loss."""
    raw = _encode(value)
    if len(raw) <= maximum:
        return value
    return {"value_omitted": True, "encoded_bytes": len(raw), "sha256": _sha(raw)}


def _pick(value, fields):
    if not isinstance(value, dict):
        return None
    return {field: _small(value[field]) for field in fields if field in value}


def _provided_boundaries(value, domain):
    if not isinstance(value, dict):
        return {"selected": {}, "omitted_fields": 0, "invalid_container": True}
    selected = {}
    for key in _BOUNDARY_FIELDS[domain]:
        if key not in value:
            continue
        item = value[key]
        if item is None or type(item) is bool or (type(item) is int and -1 <= item <= 1000000):
            selected[key] = item
        elif isinstance(item, str) and len(item.encode("utf-8")) <= 128:
            selected[key] = item
    return {"selected": selected, "omitted_fields": len(value) - len(selected), "invalid_container": False}


def _rows(values, fields, category="status"):
    if not isinstance(values, list) or len(values) > _MAX_ROWS or any(not isinstance(x, dict) for x in values):
        raise ValueError("report rows must be bounded objects")
    counts = Counter()
    indexed = []
    quiet = {"passed", "matched", "matched_rejection", "killed", "observed", "ok", "proposed"}
    for index, row in enumerate(values):
        state = row.get(category)
        if state is not None:
            state = _text(state, "row category", 128)
        label = state if state is not None else "<missing>"
        counts[label] += 1
        attention = state not in quiet or row.get("reported_status") == "failed"
        indexed.append((not attention, index, _pick(row, fields)))
    if len(counts) > 32:
        raise ValueError("too many distinct report categories")
    selected = sorted(indexed)[:_SELECTED]
    return {"received": len(values), "category_counts": dict(sorted(counts.items())),
            "selected": [{"source_index": index, **row} for _, index, row in selected],
            "omitted": max(0, len(values) - len(selected))}


def _objects(values):
    if not isinstance(values, list) or len(values) > _MAX_ROWS or any(not isinstance(x, dict) for x in values):
        raise ValueError("report rows must be bounded objects")
    return values


def _summary(report):
    schema = report["schema"]
    domain, semantics, statuses = _SPECS[schema]
    status = report.get("classification") if domain == "intermittency" else report.get("status")
    if not isinstance(status, str) or status not in statuses:
        raise ValueError("unsupported report status")
    common = ("stop_reason", "reason", "limits", "budget", "measurements")
    details = _pick(report, common)
    lists = {}
    if domain == "reproduction":
        details.update(_pick(report, ("failure_fingerprint", "failure_preserved", "minimality", "original_count",
            "reduced_count", "removed_count", "original_sha256", "reduced_sha256", "calls", "outcomes", "trace_omitted")))
        details["final_verification"] = _pick(report.get("final_verification"), ("status", "failure_fingerprint", "reason"))
        lists["trace"] = _rows(report.get("trace", []), ("call", "phase", "status", "candidate_count",
            "candidate_sha256", "failure_fingerprint_sha256", "reason"))
    elif domain == "intermittency":
        details.update(_pick(report, ("seed", "context_sha256", "attempt_count", "counts", "reported_counts", "failure_ever_reported")))
        lists["attempts"] = _rows(report.get("attempts", []), ("index", "status", "reported_status",
            "failure_signature", "signature_sha256", "context_sha256", "reported_context_sha256", "context_match",
            "failure_signature_truncated", "reason", "reason_truncated"))
        lists["failure_groups"] = _rows(report.get("failure_groups", []), ("signature_sha256", "failure_signature",
            "attempt_indices", "eligible_attempt_indices"), category="category")
    elif domain == "mutation":
        details.update(_pick(report, ("source_path", "source_sha256", "manifest_sha256", "command_sha256", "runner_kind",
            "counts", "generated_mutants", "executions", "execution_count_basis")))
        details["baseline"] = _pick(report.get("baseline"), ("status", "exit", "reason", "tests_run"))
        # Do not retain output tails; only capture metadata when present.
        for stream in ("stdout", "stderr"):
            baseline = report.get("baseline")
            if isinstance(baseline, dict) and isinstance(baseline.get(stream), dict):
                details["baseline"][stream] = _pick(baseline[stream], ("sha256", "bytes", "truncated"))
        mutations = []
        for row in _objects(report.get("mutations", [])):
            item = _pick(row.get("mutation"), ("id", "sha256", "kind", "line", "column")) or {}
            item.update(outcome=row.get("outcome"), test_result=_pick(row.get("test_result"), ("status", "exit", "reason", "tests_run")))
            mutations.append(item)
        lists["mutations"] = _rows(mutations, ("id", "sha256", "kind", "line", "column", "outcome", "test_result"), "outcome")
        lists["source_manifest"] = _rows(report.get("selected_manifest", []), ("path", "sha256"), "category")
    elif domain == "interface":
        details.update(_pick(report, ("adapter_kind", "scope", "root", "provenance")))
        coverage = report.get("coverage", {})
        details["coverage"] = _pick(coverage, ("allowed_frontier_exhausted", "global", "pending_edges", "excluded_actions"))
        goals = []
        if isinstance(coverage, dict):
            for name in ("goals_observed", "goals_not_observed"):
                values = coverage.get(name, [])
                if not isinstance(values, list) or len(values) > _MAX_ROWS:
                    raise ValueError("goals must be bounded lists")
                goals.extend({"id": goal, "status": name} for goal in values)
        lists["goals"] = _rows(goals, ("id", "status"))
        lists["transitions"] = _rows(report.get("transitions", []), ("source", "action", "target", "status", "state_changed", "reason"))
        lists["issues"] = _rows(report.get("issues", []), ("kind", "state_id", "action", "reason", "error_type"), "kind")
        details["dead_ends"] = _small(report.get("dead_ends", []))
    elif domain == "conformance":
        details.update(_pick(report, ("passed", "scope", "python_version", "python_package_version", "cloud_package_version",
            "source_files", "case_input_sha256", "case_count", "counts", "not_covered", "projection_exclusions",
            "difference_inventory", "exception_comparison", "source_unchanged_after_comparison")))
        results = []
        for row in _objects(report.get("results", [])):
            item = _pick(row, ("id", "helper", "input_sha256", "status", "differences"))
            item["python"] = _pick(row.get("python"), ("status", "error_type"))
            item["cloud"] = _pick(row.get("cloud"), ("status", "error_type"))
            results.append(item)
        lists["results"] = _rows(results, ("id", "helper", "input_sha256", "status", "differences", "python", "cloud"))
    else:
        details.update(_pick(report, ("policy", "selected_count", "omitted")))
        lists["ordered"] = _rows(report.get("ordered", []), ("label", "command_sha256", "observations", "observed_failures",
            "median_duration_ms", "heuristic_score", "original_index"), "category")
    process = report.get("process_adapter")
    if isinstance(process, dict):
        lists["process_observations"] = _rows(process.get("observations", []), ("call_ordinal", "attempt_index", "status",
            "command_sha256", "exit", "stdout_sha256", "stderr_prefix_sha256", "output_hash_covers", "reason"))
    return {"domain": domain, "reported_status": status, "status_semantics": semantics,
            "details": details, "observed_lists": lists,
            "provided_boundaries": _provided_boundaries(report.get("boundaries", {}), domain), "unknowns": list(_UNKNOWNS)}


def _identity(project_id, run_id, source_uri, source_version, schema, digest):
    if not isinstance(project_id, str) or not _PROJECT.fullmatch(project_id) or project_id == "__global__":
        raise ValueError("explicit project_id required")
    return {"project_id": project_id, "run_id": _text(run_id, "run_id", 128),
            "source_uri": _uri(source_uri), "source_version": _text(source_version, "source_version", 128),
            "report_schema": schema, "report_sha256": digest}


def _refs(documentary_refs):
    if not isinstance(documentary_refs, (list, tuple)) or len(documentary_refs) > 32:
        raise ValueError("at most 32 documentary references")
    result = []
    for row in documentary_refs:
        if not isinstance(row, dict) or set(row) - {"uri", "version", "sha256"}:
            raise ValueError("documentary refs require uri, version, optional sha256")
        digest = row.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise ValueError("invalid documentary digest")
        result.append({"uri": _uri(row.get("uri")), "version": _text(row.get("version"), "document version", 128), "sha256": digest})
    result.sort(key=lambda x: (x["uri"], x["version"], x["sha256"] or ""))
    if len({_encode(x) for x in result}) != len(result):
        raise ValueError("duplicate documentary reference")
    return result


def _key(identity, refs):
    return "verification:" + _sha(_encode({"identity": identity, "documentary_refs": refs}))


def prepare_verification_memory(report_json: str, project_id: str, run_id: str,
                                source_uri: str, source_version: str, *,
                                documentary_refs=(), expected_source_digest=None,
                                observed_at=None) -> dict:
    """Preview an unverified observation; this never opens MemoryStore.

    ``report_sha256`` covers exact supplied UTF-8 bytes, including whitespace.
    ``observed_at`` is caller observation metadata, not proof of source freshness;
    omit it to capture preparation time or supply it for deterministic output.
    """
    report, raw = _load(report_json)
    digest = _sha(raw)
    if expected_source_digest is not None and expected_source_digest != digest:
        raise ValueError("report digest mismatch")
    timestamp = time.time() if observed_at is None else observed_at
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not 0 < timestamp <= 10**12 or not math.isfinite(timestamp):
        raise ValueError("invalid observation timestamp")
    identity = _identity(project_id, run_id, source_uri, source_version, report["schema"], digest)
    refs = _refs(documentary_refs)
    result = {"schema": _SCHEMA, "status": "proposed", "identity": identity,
              "summary": _summary(report), "documentary_refs": refs,
              "observed_at": timestamp, "memory_key": _key(identity, refs),
              "boundaries": dict(_BOUNDARIES)}
    result["proposal_sha256"] = _sha(_encode(result))
    if len(_encode(result)) > _MAX_OUTPUT:
        raise ValueError("selected memory proposal exceeds output limit")
    return result


def _validate_proposal(prepared):
    fields = {"schema", "status", "identity", "summary", "documentary_refs", "observed_at", "memory_key", "boundaries", "proposal_sha256"}
    if not isinstance(prepared, dict) or set(prepared) != fields or prepared.get("schema") != _SCHEMA or prepared.get("status") != "proposed":
        raise ValueError("invalid verification memory proposal")
    unsigned = {key: value for key, value in prepared.items() if key != "proposal_sha256"}
    if len(_encode(prepared)) > _MAX_OUTPUT or prepared["proposal_sha256"] != _sha(_encode(unsigned)):
        raise ValueError("proposal integrity mismatch")
    identity = prepared["identity"]
    if not isinstance(identity, dict) or set(identity) != {"project_id", "run_id", "source_uri", "source_version", "report_schema", "report_sha256"}:
        raise ValueError("invalid proposal identity")
    schema, digest = identity["report_schema"], identity["report_sha256"]
    if schema not in _SPECS or not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise ValueError("invalid report identity")
    if _identity(identity["project_id"], identity["run_id"], identity["source_uri"], identity["source_version"], schema, digest) != identity:
        raise ValueError("invalid proposal identity")
    if prepared["boundaries"] != _BOUNDARIES or prepared["memory_key"] != _key(identity, prepared["documentary_refs"]):
        raise ValueError("invalid proposal boundary or key")
    if _refs(prepared["documentary_refs"]) != prepared["documentary_refs"]:
        raise ValueError("invalid proposal references")
    summary = prepared["summary"]
    if (not isinstance(summary, dict) or set(summary) != {"domain", "reported_status", "status_semantics", "details", "observed_lists", "provided_boundaries", "unknowns"}
            or summary.get("domain") != _SPECS[schema][0]
            or summary.get("status_semantics") != _SPECS[schema][1]
            or summary.get("reported_status") not in _SPECS[schema][2]
            or summary.get("unknowns") != _UNKNOWNS):
        raise ValueError("invalid projection contract")
    timestamp = prepared["observed_at"]
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not 0 < timestamp <= 10**12 or not math.isfinite(timestamp):
        raise ValueError("invalid proposal timestamp")


def persist_to_quarantine(prepared: dict, store: MemoryStore) -> dict:
    """Explicitly store once, through current MemoryStore v2 internals.

    A SQLite BEGIN IMMEDIATE covers lookup+existing store.store() write so two
    writers cannot silently overwrite each other. Never call get(): it commits
    access counters. The adapter refuses a caller transaction and never commits
    caller work. The proposal checksum detects accidental tampering, not a
    malicious author's ability to fabricate a new unverified report.
    """
    # Own a JSON snapshot so caller mutation cannot move identity/projection
    # while lookup and the existing store write share one atomic scope.
    try:
        raw = _encode(prepared)
        if len(raw) > _MAX_OUTPUT:
            raise ValueError("proposal exceeds output limit")
        prepared = json.loads(raw)
    except (TypeError, RecursionError, OverflowError):
        raise ValueError("proposal must be bounded JSON data") from None
    _validate_proposal(prepared)
    if not isinstance(store, MemoryStore):
        raise ValueError("an explicit existing MemoryStore is required")
    identity = prepared["identity"]
    value = {key: prepared[key] for key in ("identity", "summary", "documentary_refs", "boundaries")}
    value["schema"] = "parcimonia.verification-memory-observation/v1"
    conn = store._conn(identity["project_id"])
    if conn.in_transaction:
        raise ValueError("cannot persist inside a caller transaction")
    conn.execute("BEGIN IMMEDIATE")
    try:
        row, table = store._get_raw(conn, identity["project_id"], prepared["memory_key"])
        if row is not None:
            existing = store._row_to_entry(row)
            same = (table == "memory_quarantine" and existing.value == value
                    and existing.source_type == "tool" and existing.trust_class == "external_observation"
                    and existing.quarantined and not existing.executable_instruction
                    and existing.visibility == "private" and existing.agent_id == _AGENT
                    and existing.status == "proposal" and existing.expires_at is None
                    and existing.asset_type == "fact" and existing.category == "verification_receipt"
                    and existing.confidence == 0.0 and existing.sensitivity == 0
                    and existing.created_by == _AGENT and existing.source_ref == identity["source_version"]
                    and existing.source_id == identity["report_sha256"]
                    and existing.source_digest == identity["report_sha256"]
                    and existing.source_uri == identity["source_uri"] and existing.run_id == identity["run_id"])
            conn.rollback()
            return {"schema": "parcimonia.verification-memory-persistence/v1",
                    "status": "already_present" if same else "conflict", "writes": 0,
                    "memory_key": prepared["memory_key"], "project_id": identity["project_id"],
                    "stored_version": existing.version, "quarantined": bool(existing.quarantined)}
        entry = MemoryEntry(key=prepared["memory_key"], value=value, asset_type="fact",
                    category="verification_receipt", confidence=0.0, status="proposal",
                    visibility="private", project_id=identity["project_id"], agent_id=_AGENT,
                    source_ref=identity["source_version"], source_digest=identity["report_sha256"],
                    source_type="tool", source_uri=identity["source_uri"], source_id=identity["report_sha256"],
                    run_id=identity["run_id"], observed_at=prepared["observed_at"],
                    trust_class="external_observation", executable_instruction=False, quarantined=True,
                    created_by=_AGENT, tags=["verification", prepared["summary"]["domain"], "caller_supplied"])
        store.store(entry)
    except BaseException:
        conn.rollback()
        raise
    return {"schema": "parcimonia.verification-memory-persistence/v1", "status": "stored",
            "writes": 1, "memory_key": prepared["memory_key"], "project_id": identity["project_id"],
            "stored_version": 1, "quarantined": True}
