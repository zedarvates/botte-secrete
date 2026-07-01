"""Lazy tool loading — the ToolSearch pattern, applied to our own MCP server.

`context_profiler` measured the hidden cost: injecting every tool's full JSON
Schema into the agent's prefix (~3.8k tok for 38 tools on this repo) is paid on
every turn, on every machine, whether or not that turn uses those tools. Most
harnesses (including the one running this conversation) solve this by listing a
small core + a search tool, and resolving full schemas only on demand.

  CORE_TOOL_NAMES   the handful of tools listed unconditionally (0 lookup cost)
  find_tool(query)  lexical match over every tool's name+description (0 tokens),
                    returning the FULL schema for strong matches so one round
                    trip is enough — mirrors this harness's own ToolSearch.
  lazy_tool_list()  what `tools/list` should return in lazy mode: core + find_tool

Toggle via BOTTE_MCP_LAZY_TOOLS=0 to fall back to listing every tool (legacy
clients that don't expect a search step). tools/call always dispatches any tool
by name regardless of listing mode — lazy only affects the *catalog*, not
what's callable.
"""

from __future__ import annotations

import os
import re

# The handful of tools worth the agent always seeing — the rest are one
# find_tool() call away. Kept small on purpose; grow only for genuinely
# constant-use tools.
CORE_TOOL_NAMES = {"local_chat", "auto_route", "find_skills", "conduct"}

_WORD = re.compile(r"[a-z0-9]+")
# Common short words that would otherwise cause spurious matches (e.g. "no",
# "is") — every tool description is prose, so unfiltered stopwords make almost
# any query "match" something.
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "be", "this", "that", "it", "as", "at", "by", "from", "no", "not",
    "so", "if", "its", "such", "via", "use", "used", "0",
}


def _tokens(text: str) -> set:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _score(query_tokens: set, tool: dict) -> float:
    name_tokens = _tokens(tool["name"].replace("_", " "))
    desc_tokens = _tokens(tool.get("description", ""))
    if not query_tokens:
        return 0.0
    name_hits = len(query_tokens & name_tokens)
    desc_hits = len(query_tokens & desc_tokens)
    # name matches count triple — an agent searching "route" should find
    # auto_route/route_task above tools that merely mention routing in passing.
    return (3 * name_hits + desc_hits) / len(query_tokens)


def find_tool(query: str, tools: list, *, top_k: int = 5) -> dict:
    """Lexical search over tool name+description. 0 cloud tokens.

    Strong matches (score >= 1.0, i.e. every query token hit a tool's name)
    carry their full `inputSchema` so the agent can call them without a second
    lookup; weaker matches are name-only hints (cheap to list, keeps the
    response small when the query is broad).
    """
    query = (query or "").strip()
    qtok = _tokens(query)
    scored = sorted(
        ((_score(qtok, t), t) for t in tools),
        key=lambda x: x[0], reverse=True,
    )
    scored = [(s, t) for s, t in scored if s > 0][:top_k]

    matches = []
    for score, t in scored:
        entry = {"name": t["name"], "score": round(score, 2),
                 "description": t.get("description", "")}
        if score >= 1.0:
            entry["inputSchema"] = t.get("inputSchema")
        matches.append(entry)
    return {"query": query, "matches": matches, "cloud_tokens": 0}


def lazy_tool_list(all_tools: list) -> list:
    """What tools/list returns in lazy mode: core tools + the find_tool meta-tool."""
    core = [t for t in all_tools if t["name"] in CORE_TOOL_NAMES]
    meta = {
        "name": "find_tool",
        "description": "Find the right botte-llm MCP tool for a task by name/description "
                       "match (0 cloud tokens) — this server exposes only a small core "
                       "tool set by default; call find_tool first to discover and load "
                       "the full schema for anything else (security_scan, docs_map, "
                       "solvers, nn_audit, cwe_kb, …).",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 5}},
            "required": ["query"]},
    }
    return [meta] + core


def lazy_enabled() -> bool:
    return os.environ.get("BOTTE_MCP_LAZY_TOOLS", "1") != "0"
