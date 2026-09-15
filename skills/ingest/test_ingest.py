#!/usr/bin/env python3
"""Tests for ingest — hermetic loopback HTTP plus in-memory Qdrant.

    python -m skills.ingest.test_ingest
"""

from __future__ import annotations

import importlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from types import SimpleNamespace

from skills.ingest import extract, scrape, ingest, search, resolve_embed
from skills.ingest.ingest import _hash_embed, _embed


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            b"<html><head><title>Fixture Domain</title></head>"
            b"<body><p>Hermetic ingestion evidence.</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class _MemoryQdrant:
    def __init__(self):
        self.collections: dict[str, list[dict]] = {}

    def request(self, method, _base, path, body=None, timeout=10.0):
        del timeout
        parts = [part for part in path.split("/") if part]
        if method == "GET" and parts == ["collections"]:
            return {"result": {"collections": [
                {"name": name} for name in sorted(self.collections)
            ]}}
        if len(parts) >= 2 and parts[0] == "collections":
            collection = parts[1]
            if method == "PUT" and len(parts) == 2:
                self.collections.setdefault(collection, [])
                return {"result": True}
            if method == "PUT" and parts[2:] == ["points"]:
                self.collections.setdefault(collection, []).extend(body["points"])
                return {"result": True}
            if method == "POST" and parts[2:] == ["points", "search"]:
                return {"result": [
                    {"score": 1.0, "payload": point["payload"]}
                    for point in self.collections.get(collection, [])[:body["limit"]]
                ]}
            if method == "DELETE" and len(parts) == 2:
                self.collections.pop(collection, None)
                return {"result": True}
        return None


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

    # End-to-end transport stays on loopback; Qdrant is an in-memory contract
    # double. The test must never probe public internet or a developer LAN.
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture_url = f"http://127.0.0.1:{server.server_port}/fixture"
    memory = _MemoryQdrant()
    ingest_module = importlib.import_module("skills.ingest.ingest")
    try:
        sc = scrape(fixture_url)
        _ok("loopback scrape gets deterministic title + text",
            sc.title == "Fixture Domain"
            and "Hermetic ingestion evidence." in sc.text, state)
        with (
            patch.object(ingest_module, "_qdrant", side_effect=memory.request),
            patch.object(ingest_module, "resolve_embed", return_value=(None, None)),
        ):
            result = ingest(
                fixture_url,
                collection="botte_selftest",
                qdrant="127.0.0.1:1",
                reflect=False,
            )
            _ok("hermetic ingest stores into the Qdrant contract",
                result.get("stored") is True, state)
            hits = search(
                "fixture domain",
                collection="botte_selftest",
                qdrant="127.0.0.1:1",
            )
            _ok("hermetic search recalls the ingested document",
                len(hits.get("hits", [])) == 1
                and hits["hits"][0]["title"] == "Fixture Domain", state)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
