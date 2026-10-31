"""Pure documentary review of a supplied verification-retrieval snapshot.

URI/version equality resolves a declared reference, never source truth. Existing
inventory dependencies are reviewed separately; receipt matches create no graph
edges, storage writes, model calls or automatic context promotion.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json

from . import knowledge_links as knowledge
from . import memory_bridge as bridge
from . import memory_retrieval as retrieval


_SCHEMA = "parcimonia.verification-memory-linked-retrieval/v1"
_OUTCOMES = ("declared_reference_resolved", "version_mismatch",
             "missing_in_declared_inventory", "unknown_reference",
             "ambiguous_reference", "kind_mismatch")
_RESULT_KEYS = {"memory_key", "stored_version", "lexical_score", "summary", "source",
                "report_schema", "run_id", "documentary_refs", "stored_projection_sha256",
                "handling", "quarantined", "executable_instruction"}
_REFERENCE_KEYS = {"uri", "version", "sha256", "comparison", "basis", "digest_basis"}
_COMPARISONS = ("unknown", "version_mismatch", "digest_mismatch",
               "version_match_digest_unknown", "version_and_digest_match")
_COVERAGE_KEYS = {"scope", "scan_order", "candidate_rows_seen", "validated_rows",
                  "invalid_rows", "oversized_rows", "input_bytes", "matching_rows",
                  "omitted_matches", "scan_complete", "stop_reason"}
_LIMIT_KEYS = {"max_rows", "max_input_bytes", "max_results", "max_output_bytes",
              "max_seconds", "max_sqlite_vm_steps", "max_database_bytes", "max_sqlite_value_bytes"}
_BOUNDARIES = {"handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE", "writes": 0,
    "network": False, "model_calls": 0, "memory_promotion": False,
    "executable_instruction": False, "report_truth": "unverified",
    "report_authenticity": "unknown", "source_freshness": "unknown",
    "raw_report_digest": "declared_not_rehashed",
    "snapshot": "existing_checkpointed_sqlite_immutable_read",
    "filesystem_adversary_isolation": False}


def _encoded(value):
    # Match the CLI's wire encoding, including escaped Unicode.
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _owned(value):
    try:
        if type(value) is not dict:
            raise ValueError("a versioned JSON object is required")
        raw = _encoded(value)
        if len(raw) > 262144:
            raise ValueError("supplied snapshot exceeds input byte limit")
        return json.loads(raw), raw
    except (TypeError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError("invalid bounded JSON snapshot") from error


def _count(value):
    return type(value) is int and 0 <= value <= 10**12


def _reference(value, basis):
    if (type(value) is not dict or set(value) != _REFERENCE_KEYS
            or value.get("comparison") not in _COMPARISONS
            or value.get("basis") != "caller_declared_current_sources"
            or value.get("digest_basis") != basis):
        raise ValueError("invalid recalled reference contract")
    bridge._uri(value["uri"])
    bridge._text(value["version"], "reference version", 128)
    digest = value["sha256"]
    if digest is None and basis == "caller_declared_document_bytes":
        return
    if not isinstance(digest, str) or not bridge._SHA.fullmatch(digest):
        raise ValueError("invalid recalled reference digest")


def _summary(value, report_schema):
    expected = {"domain", "reported_status", "status_semantics", "unknowns", "details",
                "projection_omissions", "observed_lists", "projection"}
    if type(value) is not dict or set(value) != expected:
        raise ValueError("invalid recalled summary")
    spec = bridge._SPECS[report_schema]
    if (value["domain"] != spec[0] or value["reported_status"] not in tuple(spec[2])
            or value["status_semantics"] != spec[1] or value["unknowns"] != bridge._UNKNOWNS
            or value["projection"] != "canonical_status_and_typed_counters_only"):
        raise ValueError("invalid recalled status projection")
    details = value["details"]
    if type(details) is not dict or set(details) - (retrieval._DETAIL_FIELDS | {"counts", "reported_counts"}):
        raise ValueError("invalid recalled details")
    for key, item in details.items():
        if key in ("counts", "reported_counts"):
            if type(item) is not dict or set(item) - retrieval._COUNT_KEYS or any(not _count(x) for x in item.values()):
                raise ValueError("invalid recalled counts")
        elif type(item) is not bool and not _count(item):
            raise ValueError("invalid recalled scalar")
    omissions = value["projection_omissions"]
    if (type(omissions) is not dict or set(omissions) != {"detail_fields", "detail_counter_labels",
            "observed_lists", "selected_row_payloads", "category_labels"}
            or any(not _count(x) for x in omissions.values())):
        raise ValueError("invalid recalled omissions")
    lists = value["observed_lists"]
    names = {"trace", "attempts", "failure_groups", "mutations", "source_manifest", "goals",
             "transitions", "issues", "results", "ordered", "process_observations"}
    if type(lists) is not dict or set(lists) - names:
        raise ValueError("invalid recalled list projection")
    for item in lists.values():
        if type(item) is not dict or set(item) - {"received", "omitted", "category_counts",
                "selected_context_mismatch_count", "selected_reported_failure_count", "counter_basis"}:
            raise ValueError("invalid recalled list counts")
        for key, count in item.items():
            if key == "counter_basis":
                if count != "selected_bridge_rows_only_not_all_attempts":
                    raise ValueError("invalid selected counter basis")
            elif key == "category_counts":
                if type(count) is not dict or set(count) - retrieval._COUNT_KEYS or any(not _count(x) for x in count.values()):
                    raise ValueError("invalid recalled category counts")
            elif not _count(count):
                raise ValueError("invalid recalled list count")


def _validate(report):
    if (set(report) != {"schema", "status", "project_id", "query_sha256", "results", "coverage", "limits", "boundaries"}
            or report["schema"] != retrieval._SCHEMA
            or report["status"] not in ("completed", "incomplete", "unavailable")
            or report["boundaries"] != _BOUNDARIES):
        raise ValueError("unsupported retrieval snapshot")
    if not isinstance(report["project_id"], str) or not bridge._PROJECT.fullmatch(report["project_id"]):
        raise ValueError("invalid recalled project")
    if not isinstance(report["query_sha256"], str) or not bridge._SHA.fullmatch(report["query_sha256"]):
        raise ValueError("invalid recalled query digest")
    coverage, limits = report["coverage"], report["limits"]
    if (type(coverage) is not dict or set(coverage) != _COVERAGE_KEYS
            or coverage["scope"] != "selected_project_verification_quarantine_projections"
            or coverage["scan_order"] != "rowid_descending"
            or type(coverage["scan_complete"]) is not bool
            or any(not _count(coverage[key]) for key in _COVERAGE_KEYS - {"scope", "scan_order", "scan_complete", "stop_reason"})
            or (coverage["stop_reason"] is not None and (not isinstance(coverage["stop_reason"], str) or len(coverage["stop_reason"]) > 128))
            or type(limits) is not dict or set(limits) != _LIMIT_KEYS):
        raise ValueError("invalid recalled coverage or limits")
    if any(value is not None and (type(value) not in (int, float) or value < 0) for value in limits.values()):
        raise ValueError("invalid recalled limits")
    results = report["results"]
    if type(results) is not list or len(results) > 64:
        raise ValueError("invalid recalled results")
    if report["status"] == "unavailable" and results:
        raise ValueError("unavailable retrieval cannot contain results")
    seen = set()
    for row in results:
        if (type(row) is not dict or set(row) != _RESULT_KEYS
                or not isinstance(row["memory_key"], str)
                or not row["memory_key"].startswith("verification:")
                or not bridge._SHA.fullmatch(row["memory_key"][13:])
                or row["memory_key"] in seen
                or type(row["stored_version"]) is not int or row["stored_version"] < 1
                or type(row["lexical_score"]) is not int or not 1 <= row["lexical_score"] <= 32
                or row["handling"] != "UNTRUSTED_DATA_DO_NOT_EXECUTE"
                or row["quarantined"] is not True or row["executable_instruction"] is not False
                or not isinstance(row["report_schema"], str) or row["report_schema"] not in bridge._SPECS
                or not isinstance(row["stored_projection_sha256"], str) or not bridge._SHA.fullmatch(row["stored_projection_sha256"])):
            raise ValueError("invalid recalled result identity or boundary")
        seen.add(row["memory_key"])
        bridge._text(row["run_id"], "recalled run", 128)
        _reference(row["source"], "raw_report_utf8_bytes")
        _summary(row["summary"], row["report_schema"])
        refs = row["documentary_refs"]
        if type(refs) is not list or len(refs) > 32:
            raise ValueError("invalid recalled documentary refs")
        for ref in refs:
            _reference(ref, "caller_declared_document_bytes")
        if len({_encoded(ref) for ref in refs}) != len(refs):
            raise ValueError("duplicate recalled documentary ref")


def _match(ref, candidates, complete):
    typed = [node for node in candidates if node["kind"] in ("document", "recipe")]
    exact = [node for node in typed if node["source_version"] == ref["version"]]
    plausible = exact or typed or candidates
    if exact:
        status = "declared_reference_resolved" if len(exact) == 1 else "ambiguous_reference"
    elif typed:
        status = "version_mismatch" if len(typed) == 1 else "ambiguous_reference"
    elif candidates:
        status = "kind_mismatch"
    else:
        status = "missing_in_declared_inventory" if complete else "unknown_reference"
    return {"status": status, "candidate_count": len(plausible),
            "candidate_nodes": [{"id": node["id"], "kind": node["kind"],
                "source_version": node["source_version"]} for node in plausible[:8]],
            "candidates_omitted": max(0, len(plausible) - 8), "verified": False}


def review_recalled_documents(retrieval_report, inventory, *, max_output_bytes=65536):
    """Match only exact declared URI/version identities; never dereference them."""
    knowledge._limit(max_output_bytes, "max_output_bytes", 8192, 262144)
    report, raw = _owned(retrieval_report)
    _validate(report)
    supplied, _ = _owned(inventory)
    snapshot, nodes, _ = knowledge._snapshot(supplied, 512, 2048)
    graph = knowledge.review_knowledge_links(snapshot, max_nodes=512, max_links=2048,
        max_suggestions=0, max_output_bytes=min(32768, max_output_bytes // 2))
    by_uri = {}
    for node in sorted(nodes.values(), key=lambda item: item["id"]):
        by_uri.setdefault(node["source_uri"], []).append(node)
    counts = Counter({status: 0 for status in _OUTCOMES})
    comparison_findings = {kind: {"version_mismatch": 0, "digest_mismatch": 0}
                           for kind in ("report_sources", "documentary_refs")}
    for row in report["results"]:
        for kind, refs in (("report_sources", [row["source"]]), ("documentary_refs", row["documentary_refs"])):
            for ref in refs:
                if ref["comparison"] in comparison_findings[kind]:
                    comparison_findings[kind][ref["comparison"]] += 1
        row["documentary_review"] = []
        for index, ref in enumerate(row["documentary_refs"]):
            match = _match(ref, by_uri.get(ref["uri"], []), snapshot["completeness"] == "complete")
            counts[match["status"]] += 1
            row["documentary_review"].append({"reference_index": index, **match})
    candidate_omissions = sum(match["candidates_omitted"] for row in report["results"] for match in row["documentary_review"])
    incomplete = (report["status"] == "incomplete" or not report["coverage"]["scan_complete"]
        or any(report["coverage"][key] for key in ("invalid_rows", "oversized_rows", "omitted_matches"))
        or graph["status"] == "incomplete" or counts["unknown_reference"] or counts["ambiguous_reference"]
        or candidate_omissions)
    findings = (graph["status"] == "findings" or any(counts[key] for key in
        ("version_mismatch", "missing_in_declared_inventory", "kind_mismatch"))
        or any(count for values in comparison_findings.values() for count in values.values()))
    status = "unavailable" if report["status"] == "unavailable" else (
        "incomplete" if incomplete else "findings" if findings else "completed")
    result = {"schema": _SCHEMA, "status": status,
        "retrieval": {key: value for key, value in report.items() if key != "results"},
        "results": report["results"], "inventory_review": graph,
        "reference_counts": dict(counts),
        "current_source_comparison_findings": comparison_findings,
        "coverage": {"results_received": len(report["results"]), "results_included": len(report["results"]),
            "results_omitted_by_output_budget": 0, "reference_details_omitted_by_output_budget": 0,
            "reference_candidates_omitted": candidate_omissions,
            "inventory_review_status_before_wrapper_budget": graph["status"],
            "inventory_graph_details_omitted_by_wrapper_budget": 0,
            "references_reviewed": sum(counts.values()), "inventory_completeness": snapshot["completeness"],
            "reference_match_basis": "exact_declared_uri_and_version_no_content_fetch",
            "reference_digests_compared_to_inventory": False,
            "global_knowledge_coverage": "unknown"},
        "source": {"retrieval_sha256": hashlib.sha256(raw).hexdigest(),
                   "digest_basis": "canonical_supplied_retrieval_json_utf8", "verified": False},
        "limits": {"max_output_bytes": max_output_bytes, "max_candidates_per_reference": 8},
        "boundaries": {"handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE", "storage_writes": 0,
            "network_calls": 0, "model_calls": 0, "source_truth_verified": False,
            "memory_promotion": False, "executable_instruction": False,
            "receipt_matches_added_to_inventory_graph": False}}
    while len(_encoded(result)) > max_output_bytes:
        # The graph review measures UTF-8 internally. Its Unicode detail lists
        # can expand in the CLI's escaped-ASCII envelope; trim those copied
        # lists explicitly before removing a receipt and its source citations.
        if graph["links"]:
            graph["links"].pop()
            graph["links_omitted"] += 1
            graph["coverage"]["link_details_complete"] = False
        elif graph["unlinked_node_ids"]:
            graph["unlinked_node_ids"].pop()
            graph["unlinked_node_ids_omitted"] += 1
        elif graph["dependencies"]["cycle_witnesses"]:
            graph["dependencies"]["cycle_witnesses"].pop()
            graph["dependencies"]["cycle_witnesses_omitted"] += 1
        elif result["results"]:
            row = result["results"].pop()
            result["coverage"]["results_omitted_by_output_budget"] += 1
            result["coverage"]["reference_details_omitted_by_output_budget"] += len(row["documentary_refs"])
            result["coverage"]["results_included"] -= 1
            if status != "unavailable":
                result["status"] = "incomplete"
            continue
        else:
            raise ValueError("output budget cannot fit linked retrieval metadata")
        graph["status"] = "incomplete"
        result["coverage"]["inventory_graph_details_omitted_by_wrapper_budget"] += 1
        if status != "unavailable":
            result["status"] = "incomplete"
    if len(_encoded(result)) > max_output_bytes:
        raise ValueError("output budget cannot fit linked retrieval metadata")
    return result


__all__ = ["review_recalled_documents"]
