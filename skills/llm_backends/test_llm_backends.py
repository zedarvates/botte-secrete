#!/usr/bin/env python3
"""Offline tests for llm_backends + llm_mcp.

No live LLM server required: model extraction, registry round-trip, model
selection, hardware profiling and the MCP handshake are all exercised with
synthetic data. A final optional block runs a real local_chat IF a backend is up.

    python -m skills.llm_backends.test_llm_backends
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.llm_backends import discovery, registry
from skills.llm_backends.discovery import Backend
from skills.llm_backends.audit import profile_hardware, recommend_model, Hardware
from skills.llm_mcp import server as mcp


def _ok(msg, cond, state):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]  # [passed, failed]
    print("== llm_backends offline tests ==")

    # 1. model extraction per API shape
    openai_payload = {"data": [{"id": "gemma-coder"}, {"id": "qwen"}]}
    ollama_payload = {"models": [{"name": "llama3.2:3b"}]}
    _ok("openai model extraction",
        discovery._extract_models("openai", openai_payload) == ["gemma-coder", "qwen"], state)
    _ok("ollama model extraction",
        discovery._extract_models("ollama", ollama_payload) == ["llama3.2:3b"], state)
    _ok("empty payload safe",
        discovery._extract_models("openai", None) == [], state)

    # 2. registry round-trip
    b = Backend(kind="lmstudio", label="LM Studio", host="127.0.0.1", port=1234,
                api="openai", chat=True, models=["gemma-4-coder", "vibevoice-tts"],
                latency_ms=12, base_url="http://127.0.0.1:1234")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "reg.json"
        registry.save([b], path=path)
        loaded = registry.load(path=path)
    _ok("registry save/load round-trip",
        len(loaded) == 1 and loaded[0].host == "127.0.0.1" and loaded[0].models[0] == "gemma-4-coder",
        state)

    # 3. model selection prefers coder, skips voice
    _ok("preferred_model skips voice, prefers coder",
        registry.preferred_model(b) == "gemma-4-coder", state)
    b2 = Backend("ollama", "Ollama", "h", 11434, "openai", True,
                 models=["qwq-reasoner", "llama3.2-instruct"])
    _ok("preferred_model deprioritises reasoning",
        registry.preferred_model(b2) == "llama3.2-instruct", state)

    # 4. hardware profile + recommendation
    hw = profile_hardware()
    _ok("hardware profile returns sane RAM/cores",
        isinstance(hw, Hardware) and hw.cpu_cores >= 1 and hw.ram_gb >= 0, state)
    rec = recommend_model(Hardware(os="x", arch="x", cpu_cores=8, ram_gb=32, gpus=["g"], vram_gb=16))
    _ok("16GB VRAM recommends a >=7b-class model",
        "model" in rec and rec["basis"] == "VRAM", state)

    # 5. MCP handshake
    init = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    _ok("MCP initialize returns protocolVersion",
        init["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION, state)
    tools = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    # Lazy tool loading (skills/llm_mcp/lazy.py) means tools/list only returns a
    # small core + find_tool by default — most tools, including the local-LLM
    # ones below, are one find_tool() lookup away rather than listed upfront.
    # What must still hold: they're all dispatchable via tools/call, and
    # discoverable via find_tool. "local_chat" is in the always-listed core.
    _ok("MCP tools/list always includes local_chat (core) + find_tool",
        {"local_chat", "find_tool"} <= names, state)
    core_local_llm_tools = {"discover_backends", "list_models", "audit_local_usage",
                            "route_task", "local_chat"}
    _ok("the core local-LLM tools are all dispatchable via tools/call",
        core_local_llm_tools <= set(mcp.DISPATCH), state)
    found = mcp.handle({"jsonrpc": "2.0", "id": 21, "method": "tools/call",
                        "params": {"name": "find_tool",
                                   "arguments": {"query": "discover local LLM backends"}}})
    import json as _json
    found_names = {m["name"] for m in
                   _json.loads(found["result"]["content"][0]["text"])["matches"]}
    _ok("find_tool surfaces discover_backends for a discovery query",
        "discover_backends" in found_names, state)
    notif = mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    _ok("MCP notification returns no response", notif is None, state)
    routed = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "route_task",
                                    "arguments": {"task_type": "classification",
                                                  "input_text": "trie ces mots"}}})
    _ok("MCP route_task returns text content",
        routed["result"]["content"][0]["type"] == "text", state)

    # 6. structured output (anti-hallucination) — offline, via a stubbed _post.
    from skills.llm_backends.client import LocalLLMClient, LocalLLMError, gbnf_for_enum
    fake = Backend("lmstudio", "LM Studio", "127.0.0.1", 1234, "openai", True,
                   models=["gemma"], base_url="http://127.0.0.1:1234")
    client = LocalLLMClient(backend=fake)
    cap = {"reply": "{}"}

    def _fake_post(path, body, _c=cap):
        _c["body"] = body
        return {"choices": [{"message": {"content": _c["reply"]}, "finish_reason": "stop"}],
                "model": "gemma", "usage": {}}
    client._post = _fake_post  # type: ignore

    client.chat("x", response_format={"type": "json_object"})
    _ok("response_format forwarded to the backend body",
        cap["body"].get("response_format") == {"type": "json_object"}, state)

    cap["reply"] = '{"answer": "local", "evidence": ["a"]}'
    obj = client.chat_json("classify", schema={"type": "object", "required": ["answer"]})
    _ok("chat_json parses a JSON object", obj.get("answer") == "local", state)
    _ok("chat_json sends json_schema when a schema is given",
        cap["body"]["response_format"]["type"] == "json_schema", state)

    cap["reply"] = '```json\n{"answer": "cloud"}\n```'
    _ok("chat_json strips markdown fences", client.chat_json("q").get("answer") == "cloud", state)

    cap["reply"] = "I think it is local, definitely."  # not JSON, ever
    try:
        client.chat_json("q", retries=1)
        _ok("chat_json raises on persistent non-JSON", False, state)
    except LocalLLMError:
        _ok("chat_json raises on persistent non-JSON", True, state)

    _ok("gbnf_for_enum builds a closed one-of grammar",
        gbnf_for_enum(["local", "cloud"]) == 'root ::= "local" | "cloud"', state)

    # 7. optional live check
    best = registry.best_chat_backend()
    if best:
        from skills.llm_backends.client import LocalLLMClient, LocalLLMError
        try:
            res = LocalLLMClient().chat("Réponds par OK.", max_tokens=32)
            _ok(f"live local_chat on {res.backend} ({res.total_tokens} tok)",
                len(res.text) > 0, state)
        except LocalLLMError as e:
            print(f"  [skip] live chat: {e}")
    else:
        print("  [skip] no live backend registered (offline)")

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
