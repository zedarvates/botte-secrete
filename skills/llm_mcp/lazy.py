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

import copy
import json
import os
import re
import unicodedata

# The handful of tools worth the agent always seeing — the rest are one
# find_tool() call away. Kept small on purpose; grow only for genuinely
# constant-use tools.
CORE_TOOL_NAMES = {"local_chat", "auto_route", "find_skills", "conduct", "assess_task"}

MAX_QUERY_BYTES = 2048
MAX_SCHEMA_BUDGET_BYTES = 65536
DEFAULT_SCHEMA_BUDGET_BYTES = 8192
MAX_DESCRIPTION_BYTES = 384

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
    normalized = "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                         if not unicodedata.combining(c))
    return {w for w in _WORD.findall(normalized) if w not in _STOP}


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


def _utf8_prefix(text: str, limit: int) -> str:
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def find_tool(query: str, tools: list, *, top_k: int = 5,
              schema_budget_bytes: int = DEFAULT_SCHEMA_BUDGET_BYTES) -> dict:
    """Return bounded discovery hints, with full schemas only when they fit.

    The schema budget counts compact UTF-8 JSON bytes, not provider tokens.
    A deferred match remains visible and callable by name; discovery does not
    probe its backend, authorize execution or prove its capabilities.
    """
    if not isinstance(query, str) or len(query.encode("utf-8")) > MAX_QUERY_BYTES:
        raise ValueError("query must be a string of at most 2048 UTF-8 bytes")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
        raise ValueError("top_k must be an integer from 1 through 10")
    if (isinstance(schema_budget_bytes, bool) or not isinstance(schema_budget_bytes, int)
            or not 0 <= schema_budget_bytes <= MAX_SCHEMA_BUDGET_BYTES):
        raise ValueError("schema_budget_bytes must be an integer from 0 through 65536")
    query = query.strip()
    qtok = _tokens(query)
    # An exact identifier must not disappear behind noisy description matches.
    # Stable name ties make discovery independent of registration order.
    scored = sorted(
        ((_score(qtok, t), t) for t in tools),
        key=lambda x: (x[1]["name"] != query, -x[0], x[1]["name"]),
    )
    scored = [(score, tool) for score, tool in scored if score > 0][:top_k]
    matches, used = [], 0
    for score, tool in scored:
        description = tool.get("description", "")
        entry = {"name": tool["name"], "score": round(score, 2),
                 "description": _utf8_prefix(description, MAX_DESCRIPTION_BYTES),
                 "description_truncated": len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES,
                 "schema_status": "weak_match"}
        schema = tool.get("inputSchema")
        if score >= 1.0 and schema is not None:
            size = len(json.dumps(schema, ensure_ascii=False, separators=(",", ":"),
                                  allow_nan=False).encode("utf-8"))
            entry["schema_bytes"] = size
            if used + size <= schema_budget_bytes:
                entry["inputSchema"] = copy.deepcopy(schema)
                entry["schema_status"] = "included"
                used += size
            else:
                entry["schema_status"] = "deferred_budget"
        elif score >= 1.0:
            entry["schema_status"] = "unavailable"
        matches.append(entry)
    return {"query": query, "matches": matches, "cloud_tokens": 0,
            "schema_budget_bytes": schema_budget_bytes, "schema_bytes_returned": used}


def lazy_tool_list(all_tools: list) -> list:
    """What tools/list returns in lazy mode: core tools + the find_tool meta-tool."""
    core = [t for t in all_tools if t["name"] in CORE_TOOL_NAMES]
    meta = {
        "name": "find_tool",
        "description": "Find the right botte-llm MCP tool for a task by name/description "
                       "match (0 cloud tokens) — this server exposes only a small core "
                       "tool set by default; call find_tool first to discover and load "
                       "a budgeted schema for anything else (security_scan, docs_map, "
                       "solvers, nn_audit, cwe_kb, …). Deferred-budget matches remain hints; "
                       "raise schema_budget_bytes for an exact lookup. No backend probe is made.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "maxLength": 2048},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            "schema_budget_bytes": {"type": "integer", "minimum": 0,
                                    "maximum": 65536, "default": 8192}},
            "required": ["query"]},
    }
    return [meta] + core


def lazy_enabled() -> bool:
    return os.environ.get("BOTTE_MCP_LAZY_TOOLS", "1") != "0"
