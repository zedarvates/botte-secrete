"""CWE knowledge base — local RAG to enrich & de-noise security findings.

The DeepAudit idea, local-first: keep a small CWE catalog on disk and match a
finding (or any free text) to the relevant weakness — by exact id when the
analyzer already tagged one ([[fallow_like]] taint), else by **local embedding**
similarity (the [[ingest]] hash/endpoint embedding + [[vector_protocol]] cosine).
Adds the weakness name, description, and concrete mitigation to each finding so
the report explains *why* and *how to fix* — 0 cloud tokens.

  lookup(cwe_id)        exact catalog entry (deterministic)
  match(text, top_k)    best CWE entries by local-embedding similarity
  enrich(findings)      attach CWE context to taint/security findings
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> list:
    """The CWE entries (cached). Each: id, name, description, mitigation, common."""
    try:
        doc = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        return doc.get("entries", [])
    except (OSError, json.JSONDecodeError):
        return []


def _by_id() -> dict:
    return {e["id"].upper(): e for e in load_catalog()}


def lookup(cwe_id: str) -> Optional[dict]:
    """Exact catalog entry for a CWE id (e.g. 'CWE-78' or '78'). 0 tokens."""
    if not cwe_id:
        return None
    key = str(cwe_id).strip().upper()
    if not key.startswith("CWE-"):
        key = "CWE-" + key.lstrip("CWE").lstrip("-")
    return _by_id().get(key)


def _embed(text: str):
    """Local embedding (real endpoint if available, deterministic hash otherwise)."""
    from skills.ingest.ingest import _embed as embed, resolve_embed
    url, model = resolve_embed()
    vec, _dim, _src = embed(text, url, model)
    return vec


def match(text: str, *, top_k: int = 3) -> dict:
    """Rank CWE entries by local-embedding similarity to `text`. 0 cloud tokens."""
    text = (text or "").strip()
    catalog = load_catalog()
    if not text or not catalog:
        return {"matches": [], "cloud_tokens": 0}
    from skills.vector_protocol import cosine_similarity
    qv = _embed(text)
    scored = []
    for e in catalog:
        blob = f"{e['name']}. {e['description']} {' '.join(e.get('common', []))}"
        sim = cosine_similarity(qv, _embed(blob))
        scored.append((round(max(0.0, sim), 4), e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return {"matches": [{"id": e["id"], "name": e["name"], "score": s}
                        for s, e in scored[:top_k]], "cloud_tokens": 0}


def explain(cwe_id: str = "", text: str = "", *, top_k: int = 3) -> dict:
    """Explain a finding: exact CWE entry by id, or the best matches for text."""
    hit = lookup(cwe_id) if cwe_id else None
    if hit:
        return {"resolved_by": "id", "entry": hit, "cloud_tokens": 0}
    m = match(text or cwe_id, top_k=top_k)
    return {"resolved_by": "embedding", "matches": m["matches"], "cloud_tokens": 0}


def enrich(findings: list) -> list:
    """Attach CWE context (name, description, mitigation) to security findings.

    Each finding may be a dict or an object with a ``cwe`` attribute/key; when an
    id is present it's resolved exactly, otherwise by embedding-matching the
    finding's message. Returns plain dicts with a ``cwe_info`` field.
    """
    out = []
    for f in findings:
        d = f if isinstance(f, dict) else (
            f.model_dump() if hasattr(f, "model_dump") else dict(f))
        cwe_id = d.get("cwe", "")
        entry = lookup(cwe_id) if cwe_id else None
        if entry is None:
            m = match(d.get("message", ""), top_k=1)["matches"]
            entry = lookup(m[0]["id"]) if m else None
        if entry:
            d["cwe_info"] = {"id": entry["id"], "name": entry["name"],
                             "description": entry["description"],
                             "mitigation": entry["mitigation"]}
        out.append(d)
    return out
