#!/usr/bin/env python3
"""Tests for ingest — offline-deterministic + guarded live (net/Qdrant).

    python -m skills.ingest.test_ingest
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from types import SimpleNamespace

from skills.ingest import extract, scrape, ingest, search, resolve_embed
from skills.ingest.ingest import _hash_embed, _embed, _qdrant


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _net_ok() -> bool:
    try:
        urllib.request.urlopen("https://example.com", timeout=5)
        return True
    except Exception:
        return False


def _qdrant_ok(host="192.168.1.47:6333") -> bool:
    return _qdrant("GET", f"http://{host}", "/collections") is not None


def main() -> int:
    state = [0, 0]
    print("== ingest tests ==")

    # extract: strips script/style, keeps title + text
    html = "<html><head><title>Hi</title></head><body><script>x=1</script>" \
           "<p>Hello world</p><style>.a{}</style></body></html>"
    ext = extract(html)
    _ok("extract pulls title", ext["title"] == "Hi", state)
    _ok("extract keeps body text", "Hello world" in ext["text"], state)
    _ok("extract drops script/style", "x=1" not in ext["text"] and ".a" not in ext["text"], state)

    # hash embedding: deterministic + unit-normalised + fixed dim
    v1 = _hash_embed("the quick brown fox")
    v2 = _hash_embed("the quick brown fox")
    _ok("hash embed deterministic", v1 == v2, state)
    _ok("hash embed dim 256", len(v1) == 256, state)
    _ok("hash embed unit-norm", abs(sum(x * x for x in v1) - 1.0) < 1e-6, state)

    # resolve_embed: explicit url wins; registry pick needs an embedding model
    url, model = resolve_embed("http://h:1234/v1/embeddings/", "nomic")
    _ok("resolve_embed: explicit url wins (trimmed)",
        url == "http://h:1234/v1/embeddings" and model == "nomic", state)
    no_embed = [SimpleNamespace(base_url="http://a:1234", models=["qwen-instruct"])]
    _ok("resolve_embed: no embed model → (None, None)",
        resolve_embed(backends=no_embed) == (None, None), state)
    with_embed = [SimpleNamespace(base_url="http://a:1234", models=["qwen-instruct"]),
                  SimpleNamespace(base_url="http://b:1234/", models=["text-embedding-nomic"])]
    url, model = resolve_embed(backends=with_embed)
    _ok("resolve_embed: picks backend exposing an embedding model",
        url == "http://b:1234/v1/embeddings" and model == "text-embedding-nomic", state)

    # _embed: no endpoint → hash; unreachable endpoint → falls back to hash
    v, dim, src = _embed("hello world", None)
    _ok("_embed without endpoint → hash source, dim 256",
        src == "hash" and dim == 256, state)
    v, dim, src = _embed("hello world", "http://127.0.0.1:9/v1/embeddings")
    _ok("_embed unreachable endpoint → hash fallback",
        src == "hash" and dim == 256, state)

    # live (guarded)
    if _net_ok():
        sc = scrape("https://example.com")
        _ok("live scrape gets title + text",
            "Example" in sc.title and sc.chars > 0, state)
        if _qdrant_ok():
            r = ingest("https://example.com", collection="botte_selftest")
            _ok("live ingest stores into Qdrant", r.get("stored") is True, state)
            hits = search("example domain", collection="botte_selftest")
            _ok("live search recalls the ingested doc", len(hits.get("hits", [])) >= 1, state)
            # cleanup
            _qdrant("DELETE", "http://192.168.1.47:6333", "/collections/botte_selftest")
        else:
            print("  [skip] Qdrant offline — ingest/search live tests")
    else:
        print("  [skip] no network — live scrape/ingest tests")

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
