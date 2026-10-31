"""completion_proof — local, deterministic detection of unproven completion claims.

Implements anomaly A11 (completion claims without evidence markers):

  A report that asserts completion (done / complete / termine / fixed) without
  an associated proof (test_id OR cmd_output_ref OR artifact_hash OR a passed
  validation with a non-empty reference) is an anomaly.

Pure stdlib (json, re), no network, 0 LLM tokens. Every finding carries the
five mandatory policy fields: preuve, cout_estime, gain_attendu, risque,
refactoring_minimal.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPORT_EXTS = {".json", ".jsonl", ".md", ".txt", ".html"}
TEXT_NAME_RE = re.compile(
    r"(report|audit|fix|verdict|completion|status|counter|summary|verified)", re.I)
MAX_BYTES = 2_000_000

DONE_VALUES = {
    "complete", "completed", "done", "termine", "terminé", "fixed",
    "success", "successful", "passed-all",
}

CLAIM_KEY_RE = re.compile(
    r"\b(status|state|verdict|v|result|outcome)\s*[:=]\s*"
    r"""['"]?(complete[d]?|done|termin[eé]|fixed|success(ful)?)\b""",
    re.I,
)
CLAIM_WORD_RE = re.compile(
    r"\b(all checks passed|ready to commit|status:\s*complete|"
    r"task (is )?complete|termine sans|done\b|fixed\b)\b",
    re.I,
)

PROOF_FIELD_KEYS = ("test_id", "cmd_output_ref", "artifact_hash")
PROOF_TEXT_RE = re.compile(
    r"(test_id\b|cmd_output_ref\b|artifact_hash\b|"
    r"\b\d+\s+passed\b|exit_code\s*=\s*0|"
    r"pytest\b|snapshot=[0-9a-f]{8,}|git=[0-9a-f]{7,}|"
    r"sha256:[0-9a-f]{16,}|validations?.{0,40}passed)",
    re.I,
)


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _is_report_file(path: Path, root: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in REPORT_EXTS:
        return False
    if suffix in {".json", ".jsonl"}:
        return True
    if TEXT_NAME_RE.search(path.name):
        return True
    dirs = [root.name.lower(), *[part.lower() for part in path.relative_to(root).parts[:-1]]]
    return any(d in {"reports", ".botte"} for d in dirs)


def _has_structured_proof(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    proof = obj.get("proof")
    if isinstance(proof, dict) and any(
        isinstance(proof.get(k), str) and proof.get(k).strip()
        for k in PROOF_FIELD_KEYS
    ):
        return True
    if any(isinstance(obj.get(k), str) and obj.get(k).strip() for k in PROOF_FIELD_KEYS):
        return True
    completion = obj.get("completion")
    if isinstance(completion, dict):
        vals = completion.get("validations") or []
        if isinstance(vals, list) and any(
            isinstance(v, dict)
            and v.get("status") == "passed"
            and isinstance(v.get("reference"), str)
            and v["reference"].strip()
            for v in vals
        ):
            return True
    vals = obj.get("validations")
    if isinstance(vals, list) and any(
        isinstance(v, dict)
        and v.get("status") == "passed"
        and isinstance(v.get("reference"), str)
        and v["reference"].strip()
        for v in vals
    ):
        return True
    return False


def _has_structured_claim(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    for key in ("status", "state", "verdict", "v", "result", "outcome"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip().lower() in DONE_VALUES:
            return True
    if obj.get("complete") is True or obj.get("done") is True:
        return True
    return False


def _has_text_claim(text: str) -> bool:
    return bool(CLAIM_KEY_RE.search(text) or CLAIM_WORD_RE.search(text))


def _has_text_proof(text: str) -> bool:
    return bool(PROOF_TEXT_RE.search(text))


def _finding(path: str, loc: str, claim: str) -> dict:
    return {
        "type": "termine_sans_preuve",
        "f": loc,
        "preuve": f"{loc} affirme '{claim}' sans test_id/cmd_output_ref/artifact_hash",
        "cout_estime": ("confiance injustifiee propagee aux decisions suivantes ; "
                        "reprise couteuse si le manque est decouvert tard"),
        "gain_attendu": "decisions fondees sur des faits ; reprises anticipees",
        "risque": ("tres faible cote analyse — exiger la preuve peut ralentir "
                   "les clotures marginales"),
        "refactoring_minimal": ("ajouter un champ proof obligatoire (test_id OU "
                                "cmd_output_ref OU artifact_hash) et rejeter le "
                                "rapport a l'ingestion"),
        "claim": claim,
    }


def _audit_json_obj(obj, path: str, loc: str) -> list:
    if not isinstance(obj, dict):
        return []
    claimed = _has_structured_claim(obj)
    if claimed:
        claim = str(obj.get("status") or obj.get("state") or obj.get("v")
                    or obj.get("verdict") or obj.get("result") or obj.get("outcome")
                    or "complete")
    else:
        blob = json.dumps(obj, ensure_ascii=False)
        if not _has_text_claim(blob):
            return []
        claim = "marqueurs d'achevement dans le JSON"
    if _has_structured_proof(obj) or _has_text_proof(json.dumps(obj, ensure_ascii=False)):
        return []
    return [_finding(path, loc, claim)]


def _audit_text(text: str, path: str) -> list:
    if not _has_text_claim(text):
        return []
    if _has_text_proof(text):
        return []
    m = CLAIM_KEY_RE.search(text) or CLAIM_WORD_RE.search(text)
    claim = m.group(0) if m else "done"
    return [_finding(path, f"{path}:1", claim)]


def audit_file(path: Path) -> dict:
    text = _read(path)
    if text is None:
        return {"file": str(path), "findings": [],
                "error": f"{path}: unreadable or too large"}
    suffix = path.suffix.lower()
    findings: list = []
    if suffix == ".json":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            return {"file": str(path), "findings": [],
                    "error": f"{path}: JSONDecodeError ligne {exc.lineno}"}
        findings = _audit_json_obj(obj, str(path), f"{path}:1")
    elif suffix == ".jsonl":
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                if _has_text_claim(line) and not _has_text_proof(line):
                    findings.append(_finding(str(path), f"{path}:{i}", "jsonl invalide"))
                continue
            findings.extend(_audit_json_obj(obj, str(path), f"{path}:{i}"))
    else:
        findings = _audit_text(text, str(path))
    return {"file": str(path), "findings": findings}


def audit_path(target: str | Path) -> dict:
    """Audit one report file or every report-like file under a directory."""
    root = Path(target)
    if not root.exists():
        return {"error": f"no such path: {root}", "files_scanned": 0,
                "findings": [], "cloud_tokens": 0}

    if root.is_file():
        files = [root]
    else:
        files = sorted(
            p for p in root.rglob("*")
            if p.is_file() and _is_report_file(p, root)
        )
    all_findings: list = []
    errors: list = []
    scanned = 0
    for p in files:
        r = audit_file(p)
        scanned += 1
        if "error" in r:
            errors.append(r["error"])
            continue
        all_findings.extend(r["findings"])
    return {
        "target": str(root),
        "files_scanned": scanned,
        "errors": errors,
        "findings": all_findings,
        "summary": {"total": len(all_findings)},
        "cloud_tokens": 0,
    }
