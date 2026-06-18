"""LLM Endpoint Registry — persist discovered backends to configs/llm-endpoints.json.

The registry is the single source of truth that the routers (local_router,
tiered_router) and the MCP server consult to know *what is actually reachable*
instead of relying on hardcoded host:port values.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from skills.llm_backends.discovery import Backend, discover


# Repo root = three levels up from this file (skills/llm_backends/registry.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "configs" / "llm-endpoints.json"


def _backend_from_dict(d: dict) -> Backend:
    return Backend(
        kind=d["kind"], label=d.get("label", d["kind"]), host=d["host"],
        port=int(d["port"]), api=d.get("api", "openai"), chat=bool(d.get("chat", True)),
        models=list(d.get("models", [])), latency_ms=int(d.get("latency_ms", 0)),
        base_url=d.get("base_url", f"http://{d['host']}:{d['port']}"),
    )


def load(path: Optional[Path] = None) -> list[Backend]:
    """Load backends from the registry file. Empty list if none."""
    path = path or DEFAULT_REGISTRY_PATH
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [_backend_from_dict(b) for b in doc.get("backends", [])]


def save(backends: list[Backend], path: Optional[Path] = None,
         meta: Optional[dict] = None) -> Path:
    """Write backends to the registry file (pretty JSON)."""
    path = path or DEFAULT_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(backends),
        "meta": meta or {},
        "backends": [asdict(b) for b in backends],
    }
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def refresh(hosts: Optional[list[str]] = None, scan_subnet: bool = False,
            timeout: float = 1.0, path: Optional[Path] = None) -> list[Backend]:
    """Discover and persist in one call. Returns the discovered backends."""
    backends = discover(hosts=hosts, scan_subnet=scan_subnet, timeout=timeout)
    save(backends, path=path, meta={"hosts": hosts or ["127.0.0.1"],
                                    "scan_subnet": scan_subnet})
    return backends


def chat_backends(backends: Optional[list[Backend]] = None) -> list[Backend]:
    """Backends that can serve OpenAI-compatible chat completions."""
    backends = backends if backends is not None else load()
    return [b for b in backends if b.chat and b.models]


def best_chat_backend(backends: Optional[list[Backend]] = None) -> Optional[Backend]:
    """Pick the lowest-latency chat backend that has at least one model."""
    candidates = chat_backends(backends)
    if not candidates:
        return None
    return min(candidates, key=lambda b: b.latency_ms)


# Models unsuited to general text completion (voice, embeddings, transcription).
_NON_TEXT_HINTS = ("voice", "tts", "whisper", "embed", "rerank", "vision", "clip")
# Reasoning models work but burn tokens "thinking"; deprioritise as a default.
_REASONING_HINTS = ("think", "-r1", "reason", "qwq", "deepseek-r1")


def preferred_model(backend: Backend) -> Optional[str]:
    """Pick a sensible default text model from a backend's model list.

    Prefers instruct/coder models, skips voice/embedding models, and only falls
    back to a reasoning model if nothing else is available.
    """
    if not backend.models:
        return None
    text_models = [m for m in backend.models
                   if not any(h in m.lower() for h in _NON_TEXT_HINTS)]
    if not text_models:
        text_models = list(backend.models)
    non_reasoning = [m for m in text_models
                     if not any(h in m.lower() for h in _REASONING_HINTS)]
    pool = non_reasoning or text_models
    # Prefer coder/instruct flavours when present.
    for tag in ("coder", "instruct", "chat", "it"):
        for m in pool:
            if tag in m.lower():
                return m
    return pool[0]
