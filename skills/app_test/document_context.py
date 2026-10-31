"""Read explicitly catalogued local documents into bounded, cited context.

This is lexical source selection, not semantic RAG or a model route. Local text
remains untrusted data, including any instructions it contains.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from skills.app_test import knowledge_links as knowledge
from skills.completion_proof.verify import _scoped, EvidenceError


def _encode(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _refs(rows, maximum):
    if type(rows) is not list or len(rows) > maximum:
        raise ValueError("references must be a bounded list")
    result = []
    for row in rows:
        if type(row) is not dict or set(row) - {"uri", "version", "sha256"}:
            raise ValueError("invalid document reference")
        uri = knowledge._uri(row.get("uri"))
        version = knowledge._text(row.get("version"), "version", 128)
        digest = row.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid document digest")
        result.append({"uri": uri, "version": version, "sha256": digest})
    if len({_encode(row) for row in result}) != len(result):
        raise ValueError("duplicate document reference")
    return result


def _catalog(value):
    if (type(value) is not dict or set(value) != {"schema", "documents"}
            or value["schema"] != "parcimonia.local-document-catalog/v1"
            or type(value["documents"]) is not list or len(value["documents"]) > 64):
        raise ValueError("invalid local document catalog")
    if len(_encode(value)) > 131072:
        raise ValueError("document catalog exceeds byte limit")
    result = {}
    for item in value["documents"]:
        if type(item) is not dict or set(item) != {"uri", "version", "file", "sha256"}:
            raise ValueError("catalog entries need uri/version/file/sha256")
        ref = _refs([{key: item[key] for key in ("uri", "version", "sha256")}], 1)[0]
        if ref["sha256"] is None:
            raise ValueError("catalog digest is required")
        file = knowledge._text(item["file"], "file", 512)
        path = PurePosixPath(file)
        if (path.is_absolute() or "\\" in file or ":" in file
                or any(part in {"", ".", ".."} for part in file.split("/"))
                or path.suffix.lower() not in {".md", ".txt"}):
            raise ValueError("catalog file must be a relative Markdown/text path")
        key = (ref["uri"], ref["version"])
        if key in result:
            raise ValueError("ambiguous catalog identity")
        result[key] = {**ref, "file": file}
    return result


def _fingerprint(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read(root, file, allowance):
    # Reuse the existing evidence-path contract, including parent-link checks.
    path = _scoped(root, file)
    before = path.stat()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            return None, "unavailable"
        if _fingerprint(before) != _fingerprint(opened):
            return None, "source_changed"
        if opened.st_size > allowance:
            return None, "file_byte_budget"
        raw = stream.read(allowance + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > allowance or len(raw) != opened.st_size:
        return raw, "source_changed"
    if (_fingerprint(opened) != _fingerprint(after) or path.is_symlink()
            or _fingerprint(path.stat()) != _fingerprint(opened)):
        return raw, "source_changed"
    return raw, None


def prepare_document_context(references, catalog, root, query, *, max_documents=8,
                             max_file_bytes=131072, max_input_bytes=524288,
                             max_excerpt_chars=2000, max_output_bytes=32768):
    """Verify selected UTF-8 document bytes and return one cited line per match.

    File hashes cover raw bytes; excerpt hashes cover returned UTF-8 text. Read
    consistency checks do not isolate an adversarial filesystem owner.
    """
    for value, name, low, high in (
        (max_documents, "max_documents", 1, 32),
        (max_file_bytes, "max_file_bytes", 1024, 1048576),
        (max_input_bytes, "max_input_bytes", 1024, 16777216),
        (max_excerpt_chars, "max_excerpt_chars", 256, 4096),
        (max_output_bytes, "max_output_bytes", 4096, 131072)):
        knowledge._limit(value, name, low, high)
    query = knowledge._text(query, "query", 1024)
    tokens = set(re.findall(r"[^\W_]+", query.casefold()))
    if not tokens or len(tokens) > 32:
        raise ValueError("query needs 1..32 lexical tokens")
    refs = _refs(references, 32)
    entries = _catalog(catalog)
    # Own the small caller data, and bind its exact normalized selection.
    selection_digest = hashlib.sha256(_encode(refs)).hexdigest()
    catalog_digest = hashlib.sha256(_encode({"schema": "parcimonia.local-document-catalog/v1",
                                             "documents": list(entries.values())})).hexdigest()
    base = Path(os.path.abspath(root))
    if base.resolve(strict=True) != base or not base.is_dir():
        raise ValueError("root must be an existing non-symlink directory")
    rows, used, opened = [], 0, 0
    for ref in refs:
        row = {"reference": ref, "status": "not_catalogued"}
        entry = entries.get((ref["uri"], ref["version"]))
        if entry is not None:
            row["expected_sha256"] = entry["sha256"]
        if entry is None:
            if any(uri == ref["uri"] for uri, _ in entries):
                row["status"] = "version_not_catalogued"
        elif ref["sha256"] is not None and ref["sha256"] != entry["sha256"]:
            row["status"] = "reference_digest_mismatch"
        elif opened >= max_documents or used >= max_input_bytes:
            row["status"] = "input_budget"
        else:
            opened += 1
            row["file"] = entry["file"]
            try:
                raw, error = _read(base, entry["file"], min(max_file_bytes, max_input_bytes - used))
                used += len(raw) if raw is not None else 0
                row["status"] = error or "no_match"
                if error is None:
                    digest = hashlib.sha256(raw).hexdigest()
                    row["source_sha256"] = digest
                    row["content_digest_matches_catalog"] = digest == entry["sha256"]
                    if digest != entry["sha256"]:
                        row["status"] = "content_digest_mismatch"
                    else:
                        text = raw.decode("utf-8")
                        if "\x00" in text:
                            raise ValueError("binary document")
                        lines = text.splitlines()
                        best, matching_lines = None, 0
                        for index, line in enumerate(lines):
                            hits, first = set(), None
                            for word in re.finditer(r"[^\W_]+", line):
                                folded = word.group().casefold()
                                if folded in tokens:
                                    hits.add(folded)
                                    if first is None:
                                        first = word.start()
                            if hits:
                                matching_lines += 1
                                candidate = (-len(hits), index, first)
                                if best is None or candidate < best:
                                    best = candidate
                        if best is not None:
                            score, index, position = best
                            line = lines[index]
                            start = max(0, position - 100)
                            excerpt = line[start:start + max_excerpt_chars]
                            row.update(status="matched", excerpt=excerpt,
                                citation={"line": index + 1, "start_column": start + 1,
                                          "end_column_exclusive": start + len(excerpt) + 1},
                                full_line_included=start == 0 and len(excerpt) == len(line),
                                excerpt_sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                                lexical_score=-score, matching_lines=matching_lines,
                                other_lines_omitted=max(0, len(lines) - 1))
            except (OSError, EvidenceError, ValueError, UnicodeError):
                row["status"] = "unavailable"
        rows.append(row)
    counts = dict(Counter(row["status"] for row in rows))
    uncertain = {"input_budget", "file_byte_budget", "source_changed", "unavailable"}
    findings = {"not_catalogued", "version_not_catalogued", "reference_digest_mismatch", "content_digest_mismatch"}
    status = "incomplete" if uncertain & counts.keys() else "findings" if findings & counts.keys() else "completed"
    result = {"schema": "parcimonia.document-context/v1", "status": status,
        "documents": rows, "counts": counts,
        "coverage": {"references_received": len(refs), "documents_attempted": opened,
            "input_bytes": used, "documents_omitted_by_output_budget": 0,
            "corpus_coverage": "explicit_selected_references_only"},
        "source": {"selection_sha256": selection_digest, "catalog_sha256": catalog_digest,
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "digest_basis": "canonical_validated_selection_and_catalog_ascii_json_utf8", "verified": False},
        "limits": {"max_documents": max_documents, "max_file_bytes": max_file_bytes,
            "max_input_bytes": max_input_bytes, "max_excerpt_chars": max_excerpt_chars,
            "max_output_bytes": max_output_bytes, "sentinel_read_allowance": 1},
        "boundaries": {"handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE", "network_calls": 0,
            "model_calls": 0, "storage_writes": 0, "memory_promotion": False,
            "source_truth_verified": False, "source_freshness": "unknown",
            "filesystem_adversary_isolation": False}}
    return _fit(result, max_output_bytes)


def _fit(result, max_output_bytes):
    while len(_encode(result)) > max_output_bytes and result["documents"]:
        result["documents"].pop()
        result["coverage"]["documents_omitted_by_output_budget"] += 1
        result["status"] = "incomplete"
    if len(_encode(result)) > max_output_bytes:
        raise ValueError("output allowance cannot fit metadata")
    return result


def prepare_recalled_document_context(report, catalog, root, query, **budgets):
    """Select reference identities from a supplied recall; retain its uncertainty."""
    from skills.app_test import recalled_links
    owned, raw = recalled_links._owned(report)
    schema = owned.get("schema")
    if schema == "parcimonia.verification-memory-retrieval/v1":
        retrieval = owned
    elif schema == "parcimonia.verification-memory-linked-retrieval/v1":
        if (type(owned.get("retrieval")) is not dict or type(owned.get("results")) is not list
                or len(owned["results"]) > 64):
            raise ValueError("invalid linked recall selection")
        retrieval = {**owned["retrieval"], "results": []}
        for row in owned["results"]:
            if type(row) is not dict:
                raise ValueError("invalid recalled row")
            retrieval["results"].append({k: v for k, v in row.items() if k != "documentary_review"})
    else:
        raise ValueError("unsupported recall schema")
    if owned.get("status") not in ("completed", "findings", "incomplete", "unavailable"):
        raise ValueError("invalid recall status")
    recalled_links._validate(retrieval)
    selected, seen, comparisons = [], set(), Counter()
    outcomes = Counter()
    for row in retrieval["results"]:
        summary = row["summary"]
        outcomes[summary["domain"] + ":" + summary["reported_status"]] += 1
        for ref in [row["source"], *row["documentary_refs"]]:
            if ref["comparison"] in ("version_mismatch", "digest_mismatch"):
                comparisons[ref["comparison"]] += 1
        for ref in row["documentary_refs"]:
            selected_ref = {k: ref[k] for k in ("uri", "version", "sha256")}
            key = _encode(selected_ref)
            if key not in seen:
                seen.add(key)
                selected.append(selected_ref)
    result = prepare_document_context(selected, catalog, root, query, **budgets)
    result["schema"] = "parcimonia.recalled-document-context/v1"
    result["upstream"] = {"schema": schema, "status": owned["status"],
        "retrieval_status": retrieval["status"], "retrieval_coverage": retrieval["coverage"],
        "input_sha256": hashlib.sha256(raw).hexdigest(), "digest_basis": "canonical_ascii_json_utf8",
        "selected_receipts": len(retrieval["results"]), "selected_unique_references": len(selected),
        "reported_outcomes": dict(outcomes), "comparison_findings": dict(comparisons),
        "handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE", "verified": False}
    if owned["status"] == "unavailable" or retrieval["status"] == "unavailable":
        result["status"] = "unavailable"
    elif (owned["status"] == "incomplete" or retrieval["status"] == "incomplete"
            or not retrieval["coverage"]["scan_complete"]
            or any(retrieval["coverage"][key] for key in ("invalid_rows", "oversized_rows", "omitted_matches"))):
        result["status"] = "incomplete"
    elif result["status"] == "completed" and (owned["status"] == "findings" or comparisons):
        result["status"] = "findings"
    return _fit(result, budgets.get("max_output_bytes", 32768))
