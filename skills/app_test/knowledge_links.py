"""Review declared documentary links in a supplied, versioned inventory.

Source URI/version identities follow the existing provenance boundary. They are
data, never dereferenced or promoted to truth. The existing DAG cache performs
filesystem IO, so this bounded review operates on the supplied snapshot only;
it creates no graph store and runs no model, command or network request.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

_SCHEMA = "parcimonia.knowledge-inventory/v1"
_NODE_KINDS = {"capability", "recipe", "task", "document", "receipt"}
_LINK_KINDS = {"documents", "depends_on", "evidence_for", "related_to"}
_COMPLETENESS = {"complete", "partial", "unknown"}
_MAX_INPUT_BYTES = 262144
_MAX_COMPARISONS = 8192
_COMMON_TOKENS = {"capability", "recipe", "task", "document", "receipt", "doc",
                  "the", "and", "for", "of", "les", "des", "une", "pour"}


def _limit(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _text(value, name, maximum, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or (not value and not empty)
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f"{name} must be bounded text without control characters")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} exceeds UTF-8 size limit")
    return value


def _uri(value):
    value = _text(value, "source_uri", 512)
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https", "urn", "repo", "wiki", "file"}:
            raise ValueError("unsupported documentary URI scheme")
        if not parsed.netloc and not parsed.path:
            raise ValueError("documentary URI needs an identity payload")
        if any(c.isspace() for c in value):
            raise ValueError("URI must escape whitespace")
        if parsed.scheme in {"http", "https"}:
            if not parsed.hostname or parsed.username is not None or parsed.password is not None:
                raise ValueError("HTTP documentary URI needs a host without credentials")
            _ = parsed.port
    except ValueError as error:
        raise ValueError("invalid documentary source URI") from error
    return value


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _snapshot(inventory, max_nodes, max_links):
    if (type(inventory) is not dict or len(inventory) > 4
            or set(inventory) - {"schema", "completeness", "nodes", "links"}):
        raise ValueError("inventory must use the versioned input contract")
    if inventory.get("schema") != _SCHEMA:
        raise ValueError("unsupported knowledge inventory schema")
    completeness = inventory.get("completeness", "unknown")
    if not isinstance(completeness, str) or completeness not in _COMPLETENESS:
        raise ValueError("invalid inventory completeness declaration")
    raw_nodes, raw_links = inventory.get("nodes"), inventory.get("links")
    if (type(raw_nodes) is not list or type(raw_links) is not list
            or len(raw_nodes) > max_nodes or len(raw_links) > max_links):
        raise ValueError("inventory node/link input budget exceeded")
    nodes = {}
    for node in raw_nodes:
        if (type(node) is not dict or len(node) > 5
                or set(node) - {"id", "kind", "source_uri", "source_version", "title"}):
            raise ValueError("invalid knowledge node fields")
        identity = _text(node.get("id"), "node id", 128)
        if identity in nodes:
            raise ValueError("duplicate/conflicting knowledge node id")
        if not isinstance(node.get("kind"), str) or node["kind"] not in _NODE_KINDS:
            raise ValueError("unsupported knowledge node kind")
        nodes[identity] = {"id": identity, "kind": node["kind"],
                           "source_uri": _uri(node.get("source_uri")),
                           "source_version": _text(node.get("source_version"), "source_version", 128),
                           "title": _text(node.get("title", ""), "title", 256, empty=True)}
    links = []
    for link in raw_links:
        if (type(link) is not dict or len(link) > 5
                or set(link) - {"source", "target", "kind", "source_version", "target_version"}):
            raise ValueError("invalid knowledge link fields")
        if not isinstance(link.get("kind"), str) or link["kind"] not in _LINK_KINDS:
            raise ValueError("unsupported knowledge link kind")
        item = {"source": _text(link.get("source"), "link source", 128),
                "target": _text(link.get("target"), "link target", 128), "kind": link["kind"]}
        for field in ("source_version", "target_version"):
            if field in link:
                item[field] = _text(link[field], field, 128)
        links.append(item)
    snapshot = {"schema": _SCHEMA, "completeness": completeness,
                "nodes": list(nodes.values()), "links": links}
    raw = _encoded(snapshot)
    if len(raw) > _MAX_INPUT_BYTES:
        raise ValueError("inventory exceeds UTF-8 input budget")
    return snapshot, nodes, raw


def _reference(node):
    return {"source_uri": node["source_uri"], "source_version": node["source_version"]}


def _cycles(adjacency, max_depth):
    """Bounded iterative DFS witnesses, not exponential enumeration of cycles."""
    colors = {}
    witnesses = []
    back_edges = depth_omitted = 0
    for root in sorted(adjacency):
        if colors.get(root, 0):
            continue
        colors[root] = 1
        path = [root]
        positions = {root: 0}
        stack = [(root, iter(sorted(adjacency[root])))]
        while stack:
            node, targets = stack[-1]
            target = next(targets, None)
            if target is None:
                stack.pop()
                positions.pop(node)
                path.pop()
                colors[node] = 2
            elif colors.get(target) == 1:
                back_edges += 1
                if len(witnesses) < 8:
                    witnesses.append(path[positions[target]:] + [target])
            elif colors.get(target, 0) == 0:
                if len(path) >= max_depth:
                    depth_omitted += 1
                    continue
                colors[target] = 1
                positions[target] = len(path)
                path.append(target)
                stack.append((target, iter(sorted(adjacency[target]))))
    return {"cycle_status": "cycles_observed" if back_edges else (
                "unknown_depth_limit" if depth_omitted else "acyclic_in_supplied_resolved_dependencies"),
            "analysis_complete": depth_omitted == 0,
            "back_edges_observed": back_edges, "cycle_witnesses": witnesses,
            "cycle_witnesses_omitted": max(0, back_edges - len(witnesses)),
            "depth_limited_edges": depth_omitted,
            "all_cycles_enumerated": False}


def _tokens(text):
    folded = unicodedata.normalize("NFKC", text).casefold().replace("_", " ")
    return {x for x in re.findall(r"\w+", folded)[:64]
            if len(x) > 1 and x not in _COMMON_TOKENS}


def _suggest(unresolved, nodes, limit):
    suggestions = []
    comparisons = completed_queries = candidate_pairs = policy_excluded = limit_omitted = 0
    candidate_tokens = {identity: _tokens(identity + " " + node["title"])
                        for identity, node in nodes.items()}
    queries = sorted(unresolved)
    if limit:
        for query in queries:
            tokens = _tokens(query)
            candidates = []
            complete = True
            for identity in sorted(nodes):
                if comparisons >= _MAX_COMPARISONS:
                    complete = False
                    break
                comparisons += 1
                other = candidate_tokens[identity]
                if tokens & other:
                    score = len(tokens & other) / len(tokens | other)
                    candidates.append((-score, identity))
            if complete:
                completed_queries += 1
            candidate_pairs += len(candidates)
            policy_excluded += max(0, len(candidates) - 2)
            for score, identity in sorted(candidates)[:2]:
                if len(suggestions) < limit:
                    suggestions.append({"unresolved_id": query, "candidate_id": identity,
                        "candidate_ref": _reference(nodes[identity]),
                        "lexical_score": round(-score, 6), "relation": "lexical_candidate_only",
                        "advisory": True, "verified": False})
                else:
                    limit_omitted += 1
            if not complete or len(suggestions) >= limit:
                break
    return {"candidates": suggestions, "comparisons": comparisons,
            "comparison_limit": _MAX_COMPARISONS,
            "query_count": len(queries), "queries_fully_compared": completed_queries,
            "queries_not_fully_compared": len(queries) - completed_queries,
            "candidates_with_shared_tokens_observed": candidate_pairs,
            "candidates_excluded_by_per_query_policy": policy_excluded,
            "candidates_omitted_by_limit": limit_omitted,
            "candidates_omitted_by_output_budget": 0, "candidates_per_query_limit": 2,
            "added_to_declared_links": False}


def review_knowledge_links(inventory, *, max_nodes=256, max_links=1024,
                           max_depth=64, max_suggestions=16,
                           max_output_bytes=32768):
    """Review IDs/versions and declared dependencies in a caller-owned snapshot.

    Input: schema ``parcimonia.knowledge-inventory/v1``, completeness declaration,
    nodes ``{id,kind,source_uri,source_version,title?}``, and links
    ``{source,target,kind,source_version?,target_version?}``. Kinds are documents,
    depends_on, evidence_for or related_to. Only depends_on edges are cycle
    checked. A resolved reference is not an authenticated documentary claim.
    """
    _limit(max_nodes, "max_nodes", 1, 512)
    _limit(max_links, "max_links", 0, 2048)
    _limit(max_depth, "max_depth", 1, 512)
    _limit(max_suggestions, "max_suggestions", 0, 64)
    _limit(max_output_bytes, "max_output_bytes", 2048, 131072)
    snapshot, nodes, raw = _snapshot(inventory, max_nodes, max_links)
    declared_complete = snapshot["completeness"] == "complete"
    statuses = {key: 0 for key in ("resolved", "version_mismatch", "missing_in_declared_inventory", "unknown_reference")}
    adjacency = {identity: set() for identity in nodes}
    unresolved, linked, seen = set(), set(), set()
    rows = []
    duplicate_count = dependency_excluded = mismatched_constraints = unresolved_endpoints = 0
    for index, link in enumerate(snapshot["links"]):
        key = tuple(link.get(field) for field in ("source", "target", "kind", "source_version", "target_version"))
        row = {"index": index, **link, "duplicate_declaration": key in seen}
        duplicate_count += key in seen
        seen.add(key)
        missing, mismatch, unpinned = [], [], []
        for endpoint in ("source", "target"):
            identity = link[endpoint]
            if identity not in nodes:
                missing.append(endpoint)
                unresolved.add(identity)
                continue
            linked.add(identity)
            node = nodes[identity]
            row[endpoint + "_ref"] = _reference(node)
            expected = link.get(endpoint + "_version")
            if expected is None:
                unpinned.append(endpoint)
            elif expected != node["source_version"]:
                mismatch.append({"endpoint": endpoint, "expected": expected,
                                 "observed": node["source_version"]})
        row.update(missing_endpoints=missing, version_mismatches=mismatch,
                   unconstrained_endpoints=unpinned)
        mismatched_constraints += len(mismatch)
        unresolved_endpoints += len(missing)
        row["status"] = ("missing_in_declared_inventory" if declared_complete else "unknown_reference") if missing else (
            "version_mismatch" if mismatch else "resolved")
        statuses[row["status"]] += 1
        rows.append(row)
        if link["kind"] == "depends_on":
            if row["status"] == "resolved":
                adjacency[link["source"]].add(link["target"])
            else:
                dependency_excluded += 1
    dependency = _cycles(adjacency, max_depth)
    dependency["excluded_unresolved_or_stale_links"] = dependency_excluded
    priority = {"version_mismatch": 0, "missing_in_declared_inventory": 1,
                "unknown_reference": 2, "resolved": 3}
    rows.sort(key=lambda row: (priority[row["status"]], row["index"]))
    unlinked = sorted(set(nodes) - linked)
    suggestions = _suggest(unresolved, nodes, max_suggestions)
    report = {"schema": "parcimonia.knowledge-link-review/v1", "status": "completed",
        "source": {"kind": "caller_supplied_inventory", "verified": False,
                   "inventory_sha256": hashlib.sha256(raw).hexdigest(),
                   "digest_basis": "canonical_normalized_inventory_json_utf8",
                   "normalized_inventory_utf8_bytes": len(raw)},
        "coverage": {"inventory_completeness": snapshot["completeness"],
                     "inventory_declared_complete": declared_complete,
                     "reference_review_complete": True, "link_details_complete": False,
                     "completeness_declaration_verified": False,
                     "global_knowledge_coverage": "unknown"},
        "counts": {"nodes": len(nodes), "links": len(rows), **statuses,
                   "version_constraint_mismatches": mismatched_constraints,
                   "unresolved_endpoints": unresolved_endpoints,
                   "duplicate_link_declarations": duplicate_count, "unlinked_nodes": len(unlinked)},
        "links": [], "links_omitted": len(rows),
        "unlinked_node_ids": unlinked, "unlinked_node_ids_omitted": 0,
        "dependencies": dependency, "lexical_suggestions": suggestions,
        "budgets": {"max_nodes": max_nodes, "max_links": max_links,
                    "max_depth": max_depth, "max_suggestions": max_suggestions,
                    "max_output_bytes": max_output_bytes},
        "boundaries": {"execution": False, "network_calls": 0, "model_calls": 0,
                       "storage_writes": 0, "source_truth_verified": False,
                       "inferred_relations_materialized": False}}
    if statuses["unknown_reference"] or not dependency["analysis_complete"]:
        report["status"] = "incomplete"
    elif statuses["version_mismatch"] or statuses["missing_in_declared_inventory"] or dependency["back_edges_observed"]:
        report["status"] = "findings"
    semantic_status = report["status"]
    if rows:
        # The empty prefix currently omits rows. Reserve the final status width
        # before measuring; "incomplete" is longer than "completed"/"findings".
        report["status"] = "incomplete"
    trimmed_other_details = False
    while len(_encoded(report)) > max_output_bytes:
        if suggestions["candidates"]:
            suggestions["candidates"].pop()
            suggestions["candidates_omitted_by_output_budget"] += 1
        elif report["unlinked_node_ids"]:
            report["unlinked_node_ids"].pop()
            report["unlinked_node_ids_omitted"] += 1
        elif dependency["cycle_witnesses"]:
            dependency["cycle_witnesses"].pop()
            dependency["cycle_witnesses_omitted"] += 1
        else:
            raise ValueError("output budget too small for bounded summary")
        trimmed_other_details = True
        report["status"] = "incomplete"
    # Binary search a prioritized prefix instead of serializing/removing every
    # one of up to 2048 link rows. Every input link was already reviewed above.
    low, high = 0, len(rows)
    while low < high:
        middle = (low + high + 1) // 2
        report["links"] = rows[:middle]
        report["links_omitted"] = len(rows) - middle
        report["coverage"]["link_details_complete"] = middle == len(rows)
        report["status"] = "incomplete" if trimmed_other_details or middle < len(rows) else semantic_status
        if len(_encoded(report)) <= max_output_bytes:
            low = middle
        else:
            high = middle - 1
    report["links"] = rows[:low]
    report["links_omitted"] = len(rows) - low
    report["coverage"]["link_details_complete"] = low == len(rows)
    report["status"] = "incomplete" if trimmed_other_details or low < len(rows) else semantic_status
    if len(_encoded(report)) > max_output_bytes:
        raise ValueError("output budget too small for bounded summary")
    return report
