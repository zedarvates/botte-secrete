"""Optional mission gate over unchanged v1 test receipts and trusted witnesses.

The caller supplies the contract hash and witness hashes independently of the
completion claim. This checks integrity and declared scope, not the truth of an
executor's observations, review independence, or permission to close a task.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from skills.completion_proof.verify import (
    EvidenceError, MAX_JSON, _digest, _json, _read, _scoped, verify_report,
)


def _object(value, fields, code):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise EvidenceError(code)
    return value


def _text(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 256
            or any(ord(char) < 32 for char in value)):
        raise EvidenceError("invalid_identity")
    return value


def _file(root, value):
    _object(value, ("path", "sha256"), "invalid_file_binding")
    data = _read(_scoped(root, value["path"]), 8_000_000)
    if hashlib.sha256(data).hexdigest() != _digest(value["sha256"]):
        raise EvidenceError("mission_file_hash_mismatch")
    return data


def _witness(root, reference, pins):
    _text(reference)
    if reference not in pins:
        raise EvidenceError("missing_witness_pin", "missing_evidence")
    data = _read(_scoped(root, reference), MAX_JSON)
    if hashlib.sha256(data).hexdigest() != _digest(pins[reference]):
        raise EvidenceError("witness_hash_mismatch")
    return _json(data)


def criterion_witness_digest(pins: dict[str, str]) -> str:
    """Bind a review to the exact externally pinned witnesses for every criterion."""
    if not isinstance(pins, dict) or not 1 <= len(pins) <= 32:
        raise EvidenceError("invalid_criterion_pins")
    for identity, digest in pins.items():
        _text(identity)
        _digest(digest)
    return hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def verify_mission(report: str | Path, *, contract: str | Path,
                   evidence_root: str | Path, source_root: str | Path,
                   trusted_contract_sha256: str,
                   trusted_witnesses: dict[str, str]) -> dict:
    """Read-only, fail-closed mission verification; no command or review is run.

    Roots and files must remain quiescent. The trust manifest is a caller input,
    never read from the claim or inferred from a witness's own reported hash.
    """
    result = {"schema": "botte.mission-verification/v1", "verified": False,
              "status": "invalid_evidence", "errors": [], "criteria": [],
              "review_state": None, "contract_sha256": None,
              "scope": "pinned witnesses, recorded tests and listed files only",
              "authorizes_task_transition": False}
    try:
        pin = _digest(trusted_contract_sha256)
        if (not isinstance(trusted_witnesses, dict)
                or not 1 <= len(trusted_witnesses) <= 33):
            raise EvidenceError("invalid_witness_pins")
        for reference, digest in trusted_witnesses.items():
            _text(reference)
            _digest(digest)
        evidence = Path(evidence_root).resolve(strict=True)
        sources = Path(source_root).resolve(strict=True)
        if not evidence.is_dir() or not sources.is_dir():
            raise EvidenceError("invalid_root")
        data = _read(Path(contract), MAX_JSON)
        if hashlib.sha256(data).hexdigest() != pin:
            raise EvidenceError("contract_hash_mismatch")
        mission = _json(data)
        _object(mission, ("schema", "mission_id", "revision", "input", "verifier",
                          "criteria", "review"), "invalid_mission_contract")
        if mission["schema"] != "botte.verified-mission/v1":
            raise EvidenceError("unsupported_mission_schema")
        for key in ("mission_id", "revision"):
            _text(mission[key])
        _file(sources, mission["input"])
        verifier = mission["verifier"]
        _object(verifier, ("id", "version", "path", "sha256"), "invalid_verifier")
        _text(verifier["id"])
        _text(verifier["version"])
        _file(sources, {key: verifier[key] for key in ("path", "sha256")})
        criteria = mission["criteria"]
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 32:
            raise EvidenceError("invalid_criteria")
        expected = set()
        for criterion in criteria:
            _object(criterion, ("id", "description"), "invalid_criterion")
            identity = _text(criterion["id"])
            _text(criterion["description"])
            if identity in expected:
                raise EvidenceError("duplicate_criterion")
            expected.add(identity)
        review = mission["review"]
        if not isinstance(review, dict) or type(review.get("required")) is not bool:
            raise EvidenceError("invalid_review_contract")
        if review["required"]:
            _object(review, ("required", "implementer_id", "brief_sha256"),
                    "invalid_review_contract")
            _text(review["implementer_id"])
            _digest(review["brief_sha256"])
        else:
            _object(review, ("required",), "invalid_review_contract")
        claim = _json(_read(Path(report), MAX_JSON))
        _object(claim, ("schema", "status", "mission_id", "contract_sha256",
                        "criteria", "review_ref"), "invalid_mission_claim")
        if claim["schema"] != "botte.mission-completion/v1":
            raise EvidenceError("unsupported_mission_schema")
        if claim["status"] != "complete":
            raise EvidenceError("not_a_completion_claim", "announced")
        if claim["mission_id"] != mission["mission_id"] or claim["contract_sha256"] != pin:
            raise EvidenceError("mission_scope_mismatch")
        proofs = claim["criteria"]
        if not isinstance(proofs, list) or len(proofs) > 32:
            raise EvidenceError("invalid_criterion_proofs")
        indexed = {}
        for proof in proofs:
            _object(proof, ("id", "witness_ref"), "invalid_criterion_proof")
            identity = _text(proof["id"])
            if identity in indexed:
                raise EvidenceError("duplicate_criterion_proof")
            indexed[identity] = proof["witness_ref"]
        if set(indexed) != expected:
            raise EvidenceError("criterion_coverage_mismatch", "missing_evidence")
        binding = {"contract_sha256": pin, "mission_id": mission["mission_id"],
                   "revision": mission["revision"],
                   "input_sha256": mission["input"]["sha256"],
                   "verifier": {key: verifier[key] for key in ("id", "version")}}
        required_sources = {mission["input"]["path"], verifier["path"]}
        for criterion in criteria:
            identity = criterion["id"]
            witness = _witness(evidence, indexed[identity], trusted_witnesses)
            _object(witness, ("schema", "binding", "report_ref", "receipt_sha256"),
                    "invalid_criterion_witness")
            if witness["schema"] != "botte.mission-criterion/v1":
                raise EvidenceError("unsupported_mission_schema")
            if witness["binding"] != dict(binding, criterion_id=identity):
                raise EvidenceError("criterion_scope_mismatch")
            checked = verify_report(_scoped(evidence, witness["report_ref"]),
                                    evidence_root=evidence, source_root=sources,
                                    trusted_receipt_sha256=witness["receipt_sha256"])
            result["criteria"].append({"id": identity, "verification": checked})
            if (checked["verified"] is not True
                    or checked["status"] != "verified_on_recorded_tests"
                    or checked["errors"]):
                raise EvidenceError("criterion_not_verified", checked["status"])
            if not required_sources.issubset(checked["source_files_checked"]):
                raise EvidenceError("criterion_source_scope_missing")
        if review["required"]:
            if claim["review_ref"] is None:
                raise EvidenceError("missing_review", "missing_evidence")
            witness = _witness(evidence, claim["review_ref"], trusted_witnesses)
            _object(witness, ("schema", "binding", "criteria_sha256", "reviewer_id", "state",
                              "decision", "brief", "output"), "invalid_review_witness")
            if witness["schema"] != "botte.mission-review/v1":
                raise EvidenceError("unsupported_mission_schema")
            if witness["binding"] != binding:
                raise EvidenceError("review_scope_mismatch")
            expected_criteria = criterion_witness_digest(
                {identity: trusted_witnesses[reference] for identity, reference in indexed.items()})
            if witness["criteria_sha256"] != expected_criteria:
                raise EvidenceError("review_criteria_mismatch")
            _text(witness["reviewer_id"])
            if witness["reviewer_id"] == review["implementer_id"]:
                raise EvidenceError("same_reviewer_as_implementer")
            states = {"requested", "running", "failed", "interrupted", "quota_exhausted",
                      "quota_exceeded", "cancelled", "timed_out", "unknown", "completed"}
            if not isinstance(witness["state"], str) or witness["state"] not in states:
                raise EvidenceError("invalid_review_state")
            result["review_state"] = witness["state"]
            if witness["state"] != "completed":
                raise EvidenceError("review_incomplete", "review_incomplete")
            if witness["decision"] != "accepted":
                raise EvidenceError("review_not_accepted", "review_rejected")
            if not _file(evidence, witness["brief"]).strip():
                raise EvidenceError("empty_review_brief")
            if witness["brief"]["sha256"] != review["brief_sha256"]:
                raise EvidenceError("review_brief_mismatch")
            if not _file(evidence, witness["output"]).strip():
                raise EvidenceError("empty_review_output")
        elif claim["review_ref"] is not None:
            raise EvidenceError("unexpected_review")
        result.update(status="verified_on_mission_criteria", verified=True,
                      contract_sha256=pin)
    except EvidenceError as exc:
        result["status"] = exc.status
        result["errors"].append(exc.code)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        result["errors"].append("root_or_io_error")
    return result
