"""Ingest — local-first web scraping + source ingestion into Qdrant.

Two flows, both keeping the expensive cloud model out of the loop:

  scrape(url)   fetch a page, extract clean text/title locally (stdlib HTML
                parser), optionally have a LOCAL model structure it. 0 cloud tokens.
  ingest(...)   scrape (or take a file/text), reflect locally, and upsert into a
                Qdrant collection (the second-brain "foundation") for later recall.

Embeddings use a deterministic hash n-gram vector by default (no model needed, so
it always works); point `embed_url` at a local /v1/embeddings endpoint for real
semantic recall. Pure stdlib otherwise.
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

_UA = ("Mozilla/5.0 (compatible; botte-secrete-ingest/1.0; "
       "+https://github.com/zedarvates/botte-secrete)")
_EMBED_DIM = 256


# ── fetch + extract (0 tokens) ───────────────────────────────────────────────

class _Extractor(html.parser.HTMLParser):
    _SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        s = data.strip()
        if s:
            self.parts.append(s)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.parts)).strip()


def fetch(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, "replace")


def extract(html_text: str) -> dict:
    p = _Extractor()
    try:
        p.feed(html_text)
    except Exception:
        pass
    text = p.text()
    return {"title": p.title.strip(), "text": text, "chars": len(text)}


@dataclass
class Scraped:
    url: str
    title: str
    text: str
    chars: int
    structured: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


def scrape(url: str, *, structure: bool = False, max_chars: int = 12000) -> Scraped:
    raw = fetch(url)
    ext = extract(raw)
    text = ext["text"][:max_chars]
    structured = None
    if structure:
        structured = _local_structure(ext["title"], text)
    return Scraped(url=url, title=ext["title"], text=text,
                   chars=ext["chars"], structured=structured)


def _local_structure(title: str, text: str) -> Optional[dict]:
    """Ask a LOCAL model to structure scraped text (0 cloud tokens)."""
    try:
        from skills.llm_backends.client import LocalLLMClient, LocalLLMError
        from skills.llm_backends import registry
    except ImportError:
        return None
    if not registry.best_chat_backend():
        return None
    prompt = (f"Title: {title}\n\nContent:\n{text[:4000]}\n\n"
              "Summarise the above in 3 bullet points and list up to 5 key entities. "
              "Return STRICT JSON: {\"summary\": [..], \"entities\": [..]}.")
    try:
        out = LocalLLMClient().chat(prompt, max_tokens=400, temperature=0.2).text
    except LocalLLMError:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return {"summary": [out.strip()[:300]], "entities": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"summary": [out.strip()[:300]], "entities": []}


# ── embeddings (deterministic hash fallback) ─────────────────────────────────

def _hash_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Deterministic n-gram hash embedding — no model needed, always available."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for i in range(len(tokens)):
        gram = " ".join(tokens[i:i + 2])
        h = int(hashlib.sha256(gram.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _embed(text: str, embed_url: Optional[str]) -> tuple[list[float], int]:
    if embed_url:
        try:
            body = json.dumps({"input": text[:4000], "model": "local"}).encode()
            req = urllib.request.Request(embed_url, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                v = json.loads(r.read())["data"][0]["embedding"]
            return v, len(v)
        except (urllib.error.URLError, OSError, KeyError, ValueError):
            pass
    v = _hash_embed(text)
    return v, len(v)


# ── Qdrant (HTTP, stdlib) ────────────────────────────────────────────────────

def _qdrant(method: str, base: str, path: str, body: Optional[dict] = None,
            timeout: float = 10.0) -> Optional[dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def ingest(source: str, *, collection: str = "botte_ingest",
           qdrant: str = "192.168.1.47:6333", embed_url: Optional[str] = None,
           is_url: bool = True, reflect: bool = True) -> dict:
    """Ingest a URL (or file path / raw text) into Qdrant for later recall."""
    if is_url and re.match(r"^https?://", source):
        sc = scrape(source, structure=reflect)
        title, text, origin = sc.title, sc.text, source
        structured = sc.structured
    else:
        p = Path(source)
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else source
        title, origin, structured = (p.name if p.exists() else "inline"), str(source), None
        if reflect:
            structured = _local_structure(title, text[:4000])

    base = f"http://{qdrant}"
    if _qdrant("GET", base, "/collections") is None:
        return {"stored": False, "reason": f"Qdrant unreachable at {qdrant}",
                "title": title, "chars": len(text), "structured": structured}

    vector, dim = _embed(text, embed_url)
    # Ensure collection exists with the right vector size.
    _qdrant("PUT", base, f"/collections/{collection}",
            {"vectors": {"size": dim, "distance": "Cosine"}})
    pid = int(hashlib.sha256(origin.encode()).hexdigest()[:15], 16)
    res = _qdrant("PUT", base, f"/collections/{collection}/points",
                  {"points": [{"id": pid, "vector": vector,
                               "payload": {"origin": origin, "title": title,
                                           "text": text[:8000], "structured": structured,
                                           "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}}]})
    return {"stored": res is not None, "collection": collection, "id": pid,
            "title": title, "chars": len(text), "dim": dim, "structured": structured}


def search(query: str, *, collection: str = "botte_ingest",
           qdrant: str = "192.168.1.47:6333", embed_url: Optional[str] = None,
           limit: int = 5) -> dict:
    base = f"http://{qdrant}"
    vector, _ = _embed(query, embed_url)
    res = _qdrant("POST", base, f"/collections/{collection}/points/search",
                  {"vector": vector, "limit": limit, "with_payload": True})
    if res is None:
        return {"hits": [], "reason": f"Qdrant unreachable at {qdrant}"}
    hits = [{"score": round(h.get("score", 0), 3),
             "title": h.get("payload", {}).get("title", ""),
             "origin": h.get("payload", {}).get("origin", "")}
            for h in res.get("result", [])]
    return {"hits": hits}
