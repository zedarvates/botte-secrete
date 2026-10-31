"""Hermes bridge — expose the belt's core tools in two shapes so any agent
framework can use them, not just MCP clients.

botte-secrète already ships a standard MCP server (`skills.llm_mcp.server`,
stdio, JSON-RPC 2.0) — if the target framework speaks MCP, `mcp_config()`
is the entire integration: paste it into their MCP client config, done, no
code here runs. This module exists for frameworks that instead expect a flat
list of OpenAI-style function specs + a dispatcher (a common pattern for
custom "tool registry" agents that predate/don't use MCP) — Hermes-Agent's
second-brain layer ([[hermes-second-brain]]) is written against that shape,
so this bridge targets it.

    from skills.hermes_bridge import TOOL_SCHEMAS, dispatch, mcp_config
    dispatch("botte_auto_route", {"prompt": "rename x to y"})
"""

from __future__ import annotations

import json
from typing import Any

REPO_MCP_NAME = "botte-llm"


def mcp_config(python_exe: str = "python", cwd: str = ".") -> dict:
    """The zero-code path: a ready-to-paste .mcp.json entry. If Hermes-Agent
    (or whatever's on the other end) speaks MCP, this is the whole integration."""
    return {
        "mcpServers": {
            REPO_MCP_NAME: {
                "command": python_exe,
                "args": ["-m", "skills.llm_mcp.server"],
                "cwd": cwd,
            }
        }
    }


# OpenAI-function-calling-shaped specs for the focused tools the roadmap called out —
# the ones that matter for a second-brain / routing integration, not the full
# ~35-tool MCP surface (that's what `find_skills`/MCP discovery is for).
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "botte_auto_route",
        "description": "Decide local-vs-cloud for a task (0 tokens to decide). "
                       "Pass execute=true to actually run it on the chosen backend.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "task_type": {"type": "string", "default": ""},
                "execute": {"type": "boolean", "default": False},
                "max_tokens": {"type": "integer", "default": 512},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "botte_local_chat",
        "description": "Run a prompt on a local LLM (LM Studio/Ollama) — 0 cloud tokens.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "model": {"type": "string", "default": ""},
                "max_tokens": {"type": "integer", "default": 512},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "botte_fusion",
        "description": "Multi-model collaboration: cascade (cheap→escalate), "
                       "draft_refine (local drafts, cloud polishes), or vote (consensus).",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "strategy": {"type": "string", "enum": ["cascade", "draft_refine", "vote"]},
                "max_tokens": {"type": "integer", "default": 256},
            },
            "required": ["prompt", "strategy"],
        },
    },
    {
        "name": "botte_find_skills",
        "description": "0-token local search over installed skill catalogs by query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "botte_infra_tips",
        "description": "Hardware/software/MCP setup advice for running local models "
                       "on this machine.",
        "parameters": {
            "type": "object",
            "properties": {"scan_subnet": {"type": "boolean", "default": False}},
        },
    },
    {
        "name": "botte_qa_agent_run",
        "description": "Emit a privacy-safe Hermes or Codex run outcome. Backend "
                       "self-reports remain unverified; external evidence is required "
                       "before a quality label can be promoted.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "."},
                "manifest": {
                    "type": "object",
                    "description": "A botte.agent-run/v1 manifest.",
                },
            },
            "required": ["manifest"],
        },
    },
]

_NAMES = {spec["name"] for spec in TOOL_SCHEMAS}


def dispatch(name: str, args: dict[str, Any]) -> str:
    """Call the underlying botte skill for one of TOOL_SCHEMAS' tools.

    Returns a JSON string (matching what the MCP server returns), so a caller
    that already knows how to consume the MCP tool's output can reuse that
    parsing code unchanged.
    """
    if name not in _NAMES:
        return json.dumps({"error": f"unknown tool: {name}. Known: {sorted(_NAMES)}"})

    try:
        if name == "botte_auto_route":
            from skills.auto_router import auto_route, auto_run
            if args.get("execute"):
                return json.dumps(auto_run(args["prompt"], task_type=args.get("task_type", ""),
                                           max_tokens=int(args.get("max_tokens", 512))),
                                  ensure_ascii=False)
            return json.dumps(auto_route(args["prompt"], args.get("task_type", "")),
                              ensure_ascii=False)

        if name == "botte_local_chat":
            from skills.llm_backends.client import LocalLLMClient, LocalLLMError
            try:
                res = LocalLLMClient().chat(args["prompt"], model=args.get("model") or None,
                                            max_tokens=int(args.get("max_tokens", 512)))
            except LocalLLMError as e:
                return json.dumps({"error": str(e)})
            return json.dumps({"text": res.text, "model": res.model,
                               "tokens": res.total_tokens}, ensure_ascii=False)

        if name == "botte_fusion":
            from skills.auto_router import fusion
            fn = {"cascade": fusion.cascade, "draft_refine": fusion.draft_refine,
                  "vote": fusion.vote}.get(args.get("strategy", ""))
            if not fn:
                return json.dumps({"error": "strategy must be cascade | draft_refine | vote"})
            return json.dumps(fn(args["prompt"], max_tokens=int(args.get("max_tokens", 256))),
                              ensure_ascii=False)

        if name == "botte_find_skills":
            from skills.skill_finder import find
            return json.dumps(find(args["query"], top_k=int(args.get("top_k", 5))),
                              ensure_ascii=False)

        if name == "botte_infra_tips":
            from skills.infra_advisor import advise
            return json.dumps(advise(scan_subnet=bool(args.get("scan_subnet", False))),
                              ensure_ascii=False)

        if name == "botte_qa_agent_run":
            from skills.trajectory.agent_run import emit_agent_run
            return json.dumps(
                emit_agent_run(args["manifest"], project_root=args.get("project", ".")),
                ensure_ascii=False,
            )
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})

    return json.dumps({"error": f"unhandled tool: {name}"})
