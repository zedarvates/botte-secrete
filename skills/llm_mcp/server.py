"""Botte Secrète — Local LLM MCP server (stdio, JSON-RPC 2.0, stdlib only).

Exposes the llm_backends capabilities as Model Context Protocol tools so any MCP
client (Claude Code, Cursor, etc.) can:

    discover_backends   scan localhost/network for LM Studio, Ollama, …
    list_models         list models the registered backends expose
    audit_local_usage   are local models used? + hardware-aware setup advice
    route_task          recommend a tier/backend for a task (cost-aware)
    local_chat          run a prompt on a local model  ← offloads cloud tokens

Implements the minimal MCP handshake: initialize → tools/list → tools/call.
Newline-delimited JSON-RPC over stdin/stdout. No third-party dependencies.

Register in Claude Code (.mcp.json or settings):
    {
      "mcpServers": {
        "botte-llm": {
          "command": "python",
          "args": ["-m", "skills.llm_mcp.server"],
          "cwd": "/path/to/botte-secrete"
        }
      }
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the repo importable whether launched as `-m` or as a bare script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.llm_backends import registry  # noqa: E402
from skills.llm_backends.audit import audit  # noqa: E402
from skills.llm_backends.client import LocalLLMClient, LocalLLMError  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "botte-llm", "version": "1.0.0"}

# ── Tool definitions (MCP inputSchema = JSON Schema) ─────────────────────────

TOOLS = [
    {
        "name": "discover_backends",
        "description": "Scan for local LLM servers (LM Studio, Ollama, LocalAI, "
                       "vLLM, llama.cpp, ComfyUI, Qdrant) on localhost or the "
                       "network, and register what is reachable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hosts": {"type": "array", "items": {"type": "string"},
                          "description": "Explicit hosts/IPs to probe. Default: 127.0.0.1."},
                "scan_subnet": {"type": "boolean",
                                "description": "Also sweep the local /24 network."},
            },
        },
    },
    {
        "name": "list_models",
        "description": "List the models exposed by registered local backends.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "audit_local_usage",
        "description": "Report whether local models are in use, profile the host "
                       "hardware (RAM/VRAM/GPU), and give hardware-aware setup steps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fresh": {"type": "boolean", "description": "Rediscover now."},
                "scan_subnet": {"type": "boolean"},
            },
        },
    },
    {
        "name": "route_task",
        "description": "Recommend the cheapest model tier for a task and whether it "
                       "can be served by a local backend (to save cloud tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {"type": "string",
                              "description": "e.g. simple_qa, classification, code_review, "
                                             "architecture, security_audit."},
                "input_text": {"type": "string"},
                "complexity": {"type": "number", "description": "0.5 simple … 2.0 complex."},
            },
            "required": ["task_type", "input_text"],
        },
    },
    {
        "name": "local_chat",
        "description": "Run a prompt on a local model and return the result. Use for "
                       "classification, extraction, summaries, simple Q&A — keeps cloud "
                       "token usage at zero for that call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "system": {"type": "string"},
                "model": {"type": "string", "description": "Model id; default = backend's first."},
                "max_tokens": {"type": "integer", "default": 1024},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "auto_route",
        "description": "Auto-decide whether a task should run on a LOCAL model or a "
                       "CLOUD model (DeepSeek, GLM, Nemotron, Grok, Gemma, …) based on "
                       "an automatic effort estimate, then optionally execute it. "
                       "Cloud models need an API key (OPENROUTER_API_KEY or native).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "task_type": {"type": "string", "description": "Optional hint, e.g. code_review."},
                "execute": {"type": "boolean", "description": "Run it (true) or just decide (false)."},
                "max_tokens": {"type": "integer", "default": 512},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "fusion",
        "description": "Run a multi-model fusion strategy. cascade: cheap/local first, "
                       "escalate if low-confidence. draft_refine: local drafts, a stronger "
                       "cloud model refines. vote: ask several models, return consensus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "enum": ["cascade", "draft_refine", "vote"]},
                "prompt": {"type": "string"},
                "max_tokens": {"type": "integer", "default": 256},
            },
            "required": ["strategy", "prompt"],
        },
    },
]


# ── Tool implementations ─────────────────────────────────────────────────────

def _tool_discover_backends(args: dict) -> str:
    backends = registry.refresh(
        hosts=args.get("hosts") or None,
        scan_subnet=bool(args.get("scan_subnet", False)),
    )
    return json.dumps({
        "count": len(backends),
        "backends": [b.to_dict() for b in backends],
    }, ensure_ascii=False, indent=2)


def _tool_list_models(_args: dict) -> str:
    backends = registry.load()
    out = {f"{b.label} ({b.host}:{b.port})": b.models for b in backends}
    if not out:
        return "Registry empty — run discover_backends first."
    return json.dumps(out, ensure_ascii=False, indent=2)


def _tool_audit_local_usage(args: dict) -> str:
    return json.dumps(
        audit(fresh=bool(args.get("fresh", False)),
              scan_subnet=bool(args.get("scan_subnet", False))),
        ensure_ascii=False, indent=2,
    )


def _tool_route_task(args: dict) -> str:
    from skills.tiered_router import TieredRouter, Tier  # local import: heavier module
    router = TieredRouter()
    decision = router.route(
        args["task_type"], args.get("input_text", ""),
        complexity=float(args.get("complexity", 1.0)),
    )
    decision = dict(decision)
    decision["tier"] = decision["tier"].name if isinstance(decision["tier"], Tier) else decision["tier"]
    if "original_tier" in decision and isinstance(decision["original_tier"], Tier):
        decision["original_tier"] = decision["original_tier"].name
    # Attach a concrete local backend/model when local routing is possible.
    if decision.get("local_available"):
        best = registry.best_chat_backend()
        if best:
            decision["suggested_backend"] = f"{best.host}:{best.port}"
            decision["suggested_model"] = registry.preferred_model(best)
    return json.dumps(decision, ensure_ascii=False, indent=2)


def _tool_local_chat(args: dict) -> str:
    try:
        res = LocalLLMClient().chat(
            args["prompt"], system=args.get("system"),
            model=args.get("model"), max_tokens=int(args.get("max_tokens", 1024)),
        )
    except LocalLLMError as e:
        return f"ERROR: {e}"
    note = " (truncated)" if res.truncated else ""
    return (f"[{res.backend} · {res.model} · {res.total_tokens} local tok{note}]\n"
            f"{res.text}")


def _tool_auto_route(args: dict) -> str:
    from skills.auto_router import auto_route, auto_run
    if args.get("execute"):
        return json.dumps(auto_run(args["prompt"], task_type=args.get("task_type", ""),
                                   max_tokens=int(args.get("max_tokens", 512))),
                          ensure_ascii=False, indent=2)
    return json.dumps(auto_route(args["prompt"], args.get("task_type", "")),
                      ensure_ascii=False, indent=2)


def _tool_fusion(args: dict) -> str:
    from skills.auto_router import fusion
    fn = {"cascade": fusion.cascade, "draft_refine": fusion.draft_refine,
          "vote": fusion.vote}.get(args.get("strategy", ""))
    if not fn:
        return "ERROR: strategy must be cascade | draft_refine | vote"
    return json.dumps(fn(args["prompt"], max_tokens=int(args.get("max_tokens", 256))),
                      ensure_ascii=False, indent=2)


DISPATCH = {
    "discover_backends": _tool_discover_backends,
    "list_models": _tool_list_models,
    "audit_local_usage": _tool_audit_local_usage,
    "route_task": _tool_route_task,
    "local_chat": _tool_local_chat,
    "auto_route": _tool_auto_route,
    "fusion": _tool_fusion,
}


# ── JSON-RPC / MCP plumbing ──────────────────────────────────────────────────

def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(request: dict):
    """Return a response dict, or None for notifications (no reply)."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method in ("notifications/initialized", "initialized"):
        return None  # notification — no response

    if method == "ping":
        return _result(req_id, {})

    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        fn = DISPATCH.get(name)
        if not fn:
            return _error(req_id, -32602, f"Unknown tool: {name}")
        try:
            text = fn(args)
            return _result(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception as e:  # surface tool errors as MCP tool errors
            return _result(req_id, {
                "content": [{"type": "text", "text": f"ERROR: {e}"}],
                "isError": True,
            })

    if req_id is None:
        return None  # unknown notification
    return _error(req_id, -32601, f"Method not found: {method}")


def main() -> int:
    # stdout must carry only JSON-RPC; ensure UTF-8 and no buffering surprises.
    for stream in (sys.stdout, sys.stderr):
        rc = getattr(stream, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
