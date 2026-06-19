"""docgen — local drafts documentation, the cloud refines it; plus session review.

The video's pattern, mapped onto our fusion: documentation is verbose, so let the
LOCAL model write the first draft (0 cloud tokens) and only spend the cloud model
on a final correctness/polish pass. With no cloud key, you still get the local
draft (and it's marked as un-refined).

  draft_doc(topic, kind)      local draft → cloud refine of a doc
  session_review(transcript)  summarise locally what a session did (0 cloud tokens)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_KIND_BRIEF = {
    "readme": "a project README (what it is, install, usage, key features)",
    "module": "module/API documentation (purpose, public functions, examples)",
    "changelog": "a CHANGELOG entry (grouped Added/Changed/Fixed bullets)",
    "guide": "a how-to guide (goal, prerequisites, numbered steps, pitfalls)",
    "adr": "an Architecture Decision Record (context, decision, consequences)",
}


def draft_doc(topic: str, *, kind: str = "guide", context: str = "",
              max_tokens: int = 1200) -> dict:
    """Local model drafts the doc; a stronger model refines it (fusion.draft_refine)."""
    brief = _KIND_BRIEF.get(kind, _KIND_BRIEF["guide"])
    prompt = (f"Write {brief} as clean Markdown.\n\nTopic: {topic}\n"
              + (f"\nContext:\n{context}\n" if context else "")
              + "\nBe concrete and concise; no filler.")
    try:
        from skills.auto_router import fusion
    except ImportError:
        return {"error": "auto_router/fusion unavailable"}
    res = fusion.draft_refine(prompt, max_tokens=max_tokens)
    return {"kind": kind, "topic": topic,
            "draft": res.get("draft", ""), "doc": res.get("answer", ""),
            "refined_by": res.get("refined_by", "none"),
            "drafted_locally": res.get("drafted_locally", False),
            "cloud_tokens_note": "draft is local (0 cloud); refine uses cloud only if a key is set"}


# ── session review ────────────────────────────────────────────────────────────

def _load_transcript(source: str, is_file: bool) -> str:
    """Return plain text from a transcript: JSONL (Claude Code), .md, or raw text."""
    if not is_file:
        return source
    p = Path(source)
    if not p.exists():
        return source
    raw = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix == ".jsonl" or raw.lstrip().startswith("{"):
        lines = []
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                continue
            # Claude Code transcript entries: {type, message:{role, content}}
            msg = obj.get("message", obj)
            role = msg.get("role") or obj.get("type", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content
                                   if isinstance(c, dict) and c.get("type") == "text")
            if isinstance(content, str) and content.strip():
                lines.append(f"{role}: {content.strip()}")
        return "\n".join(lines)
    return raw


def session_review(source: str, *, is_file: bool = True, max_tokens: int = 500,
                   max_chars: int = 8000) -> dict:
    """Summarise locally what a session did. 0 cloud tokens."""
    text = _load_transcript(source, is_file)
    if not text.strip():
        return {"error": "empty transcript"}
    # Use the tail (most recent) when long.
    snippet = text[-max_chars:]
    try:
        from skills.llm_backends.client import LocalLLMClient, LocalLLMError
        from skills.llm_backends import registry
    except ImportError:
        return {"error": "llm_backends unavailable"}
    if not registry.best_chat_backend():
        return {"error": "no local backend — install LM Studio/Ollama", "chars": len(text)}

    prompt = ("Review this work session transcript. Return STRICT JSON with keys: "
              "\"done\" (bullet list of what was accomplished), \"decisions\" "
              "(notable choices), \"learnings\" (reusable lessons), \"next\" "
              "(suggested next steps). Be concise.\n\n" + snippet)
    try:
        out = LocalLLMClient().chat(prompt, max_tokens=max_tokens, temperature=0.2).text
    except LocalLLMError as e:
        return {"error": str(e)}
    m = re.search(r"\{.*\}", out, re.S)
    review = None
    if m:
        try:
            review = json.loads(m.group(0))
        except json.JSONDecodeError:
            review = None
    return {"cloud_tokens": 0, "chars": len(text),
            "review": review or {"summary": out.strip()[:800]}}
