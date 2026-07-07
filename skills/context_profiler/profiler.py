"""context_profiler — always-on prefix cost, project-level and host-level.

Two modes:
- `profile(project)` → project-level: directives, core_agent, tool_schemas, skill_catalog
- `profile_host(project)` → adds host-level estimation: system_reminder, memory_block,
  user_profile, host_skill_catalog, mcp_server_descriptions

The host prefix is what the runtime (Hermes) injects BEFORE the project sees any
tokens — the persona, the full skill catalog (>400 skills), MCP server descriptions,
memory context, user profile. This is "what the host imposes" vs "what botte controls".

All 0 cloud tokens. Pure estimation with stdlib.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

DEFAULT_WINDOWS = {"64k": 65_536, "128k": 131_072, "256k": 262_144}
_KEPT_CORE_TOOLS = 5


def _tok(text: str) -> int:
    return max(0, len(text or "") // 4)


# ── project-level measurements ─────────────────────────────────────────

def _tool_schema_tokens() -> tuple[int, int, int]:
    """(#tools, full-catalog tokens, actual lazy-mode tokens) for botte-llm's MCP
    tools. Lazy loading (skills/llm_mcp/lazy.py) is real, not hypothetical, so this
    measures what tools/list actually returns in lazy mode rather than estimating."""
    try:
        from skills.llm_mcp.server import TOOLS
        from skills.llm_mcp.lazy import lazy_tool_list
    except Exception:
        return 0, 0, 0
    full = sum(_tok(json.dumps(t, ensure_ascii=False)) for t in TOOLS)
    lazy = sum(_tok(json.dumps(t, ensure_ascii=False)) for t in lazy_tool_list(TOOLS))
    return len(TOOLS), full, lazy


def _skill_catalog_tokens() -> tuple[int, int]:
    try:
        from skills.skill_finder import load_catalog
    except Exception:
        return 0, 0
    cat = load_catalog()
    return len(cat), sum(_tok(getattr(s, "description", "")) for s in cat)


def _directives_tokens(project: Path) -> int:
    try:
        from skills.metrics import collect
        return int(collect(project).always_on_tokens)
    except Exception:
        return 0


def _core_agent_tokens(project: Path) -> int:
    for cand in (project / "core-agent.md", project / "skills" / "core-agent.md"):
        if cand.exists():
            return _tok(cand.read_text(encoding="utf-8", errors="replace"))
    return 0


# ── host-level estimation ──────────────────────────────────────────────

def _estimate_system_reminder() -> int:
    """Estimate the Hermes persona + tool-use enforcement + workflow rules.
    
    This is the block that starts with "You are an AI agent..." and includes
    tool schemas, skill catalog, workflow rules, parallel tool calls, etc.
    We estimate based on known structure sizes from Hermes Agent's system prompt.
    """
    # Core persona: ~200 tok
    persona = 200
    # Tool-use enforcement block: ~150 tok
    tool_enforcement = 150
    # Workflow rules + skills mandatory: ~250 tok
    workflow_rules = 250
    # Parallel tool calls instruction: ~100 tok
    parallel = 100
    # Mid-turn steering: ~120 tok
    mid_turn = 120
    # Skills delimiter + available_skills header: ~50 tok
    skills_header = 50
    # Finishing the job section: ~250 tok
    finishing = 250
    # Holographic memory section: ~100 tok
    holographic = 100
    # CLI mode instructions: ~80 tok
    cli_mode = 80
    # WSL context: ~60 tok
    wsl_context = 60
    # Profile context: ~50 tok
    profile_header = 50
    return persona + tool_enforcement + workflow_rules + parallel + mid_turn + \
           skills_header + finishing + holographic + cli_mode + wsl_context + profile_header


def _estimate_host_skill_catalog() -> tuple[int, int]:
    """Estimate the host-level skill catalog (Anthropic + plugin skills, NOT botte skills).
    
    Hermes injects the full available_skills list in every turn. This can be 400+
    skills each with a short description. We estimate based on typical Hermes
    skill catalog sizes observed in sessions.
    """
    # Estimate host skills: Hermes skills in ~/.hermes/skills/
    # (EXCLUDING botte's own skills — those are in the project skill_catalog)
    hermes_skills_dir = Path.home() / ".hermes" / "skills"
    host_count = 0
    host_tokens = 0
    if hermes_skills_dir.exists():
        try:
            skill_files = list(hermes_skills_dir.glob("**/SKILL.md"))
            host_count = len(skill_files)
            # Average SKILL.md description is ~80 chars = ~20 tok
            host_tokens = host_count * 20
        except (OSError, PermissionError):
            # Permission denied — estimate conservatively
            host_count = 250
            host_tokens = host_count * 20

    return host_count, host_tokens


def _estimate_mcp_server_descriptions(project: Path) -> int:
    """Estimate token cost of MCP server descriptions injected by the host.
    
    MCP servers in 'awaiting connection' state have long descriptions that
    are injected even when unused. We scan for MCP configs to estimate.
    """
    tokens = 0
    n_servers = 0

    # Check project .mcp.json
    for mcp_file in (project / ".mcp.json", project / "mcp.json"):
        if mcp_file.exists():
            try:
                cfg = json.loads(mcp_file.read_text(encoding="utf-8"))
                servers = cfg.get("mcpServers", cfg)
                for name, srv in servers.items():
                    desc = srv.get("description", "")
                    tokens += _tok(desc)
                    n_servers += 1
            except (json.JSONDecodeError, OSError):
                pass

    # Also check Hermes MCP servers (the ones in the session prefix)
    # We can't read ~/.hermes/mcp.json directly, but we can estimate
    # based on known Hermes MCP servers (hailo, localai, qdrant, etc.)
    # These are injected with their tool descriptions
    known_hermes_mcp = [
        ("hailo_vision", 3),   # ~3 tools, ~200 tok descriptions
        ("localai", 4),
        ("qdrant", 2),
        ("turboquant", 4),
        ("n8n", 2),
        ("hostinger", 2),
    ]
    for name, tool_count in known_hermes_mcp:
        # ~50 tok per tool description on average
        tokens += tool_count * 50
        n_servers += 1

    return tokens


def _estimate_memory_block() -> int:
    """Estimate the memory context block injected by Hermes.
    
    The <memory-context> block contains holographic memory entries.
    We estimate based on typical memory size (~2,200 chars = ~550 tok for 99% full).
    """
    # Typical memory block: ~2,180 chars for 99% full = ~545 tok
    # Plus the XML wrapper: ~50 tok
    return 545 + 50


def _estimate_user_profile() -> int:
    """Estimate the USER PROFILE block injected by Hermes.
    
    Typical profile: ~1,114 chars for 81% full = ~278 tok
    """
    return 278


# ── shared summary logic ───────────────────────────────────────────────

def _pct(total: int, windows: dict) -> dict:
    return {name: round(100 * total / size, 1) for name, size in windows.items()}


def _build_reduction_plan(components: dict) -> list[dict]:
    """Build reduction levers from components."""
    ts = components.get("tool_schemas", 0)
    n_tools = components.get("_n_tools", 0)
    ts_lazy = components.get("_tool_schemas_lazy")  # real measurement, if available
    sc = components.get("skill_catalog", 0)
    hsc = components.get("host_skill_catalog", 0)
    hsc_n = components.get("_n_host_skills", 0)
    mcpd = components.get("mcp_servers", 0)

    # Reduction levers. Prefer the ACTUAL lazy-mode measurement (lazy loading is
    # implemented — skills/llm_mcp/lazy.py) over a formula estimate.
    plan = []
    if ts_lazy is not None:
        lazy_tools_saved = max(0, ts - int(ts_lazy))
        lazy_how = ("lazy tool loading is implemented (skills/llm_mcp/lazy.py): "
                    "tools/list already returns only the core set + find_tool(query) — "
                    "this is the measured saving, not an estimate")
    elif n_tools > _KEPT_CORE_TOOLS:
        lazy_tools_saved = int(ts * (1 - _KEPT_CORE_TOOLS / n_tools))
        lazy_how = (f"expose ~{_KEPT_CORE_TOOLS} core tools + find_tool(query); "
                    "load a schema on demand (this harness's ToolSearch pattern)")
    else:
        lazy_tools_saved = 0
        lazy_how = ""
    if lazy_tools_saved:
        plan.append({"lever": "lazy tool loading",
                     "applies_to": "tool_schemas",
                     "saves_tokens": lazy_tools_saved,
                     "measured": ts_lazy is not None,
                     "how": lazy_how})
    if sc:
        plan.append({"lever": "on-demand skill search",
                     "applies_to": "skill_catalog",
                     "saves_tokens": sc,
                     "how": "use find_skills / context_budget to load only relevant skills"})
    # Host-level levers
    if hsc:
        plan.append({"lever": "host skill catalog slim-down",
                     "applies_to": "host_skill_catalog",
                     "saves_tokens": hsc,
                     "how": f"host injects ~{hsc_n} skill descriptions every turn; "
                            "the host should use find_skills pattern (keyword search) "
                            "instead of listing all skills"})
    if mcpd > 500:
        plan.append({"lever": "MCP server lazy descriptions",
                     "applies_to": "mcp_servers",
                     "saves_tokens": mcpd // 2,
                     "how": "deferred MCP servers should not inject full descriptions; "
                            "only list their names until a tool is called"})

    return plan


def summarize(components: dict, windows: dict | None = None) -> dict:
    windows = windows or DEFAULT_WINDOWS
    total = sum(int(v) for k, v in components.items() if not k.startswith("_"))
    plan = _build_reduction_plan(components)
    minimal = total - sum(p["saves_tokens"] for p in plan)

    return {
        "components": {k: v for k, v in components.items() if not k.startswith("_")},
        "total_prefix_tokens": total,
        "window_pct": _pct(total, windows),
        "reduction_plan": plan,
        "minimal_prefix_tokens": minimal,
        "reducible_tokens": total - minimal,
        "minimal_window_pct": _pct(minimal, windows),
        "cloud_tokens": 0,
    }


# ── public API ─────────────────────────────────────────────────────────

def profile(project: str | Path = ".", windows: dict | None = None) -> dict:
    """Measure the always-on project-level prefix."""
    project = Path(project).resolve()
    n_tools, tool_tok, tool_tok_lazy = _tool_schema_tokens()
    n_skills, skill_tok = _skill_catalog_tokens()
    components = {
        "directives": _directives_tokens(project),
        "core_agent": _core_agent_tokens(project),
        "tool_schemas": tool_tok,
        "skill_catalog": skill_tok,
        "_tool_schemas_lazy": tool_tok_lazy,
        "_n_tools": n_tools,
        "_n_skills": n_skills,
    }
    out = summarize(components, windows)
    out["project"] = str(project)
    out["counts"] = {"tools": n_tools, "skills": n_skills}
    return out


def profile_host(project: str | Path = ".", windows: dict | None = None) -> dict:
    """Measure project-level + host-level prefix.
    
    Returns same structure as profile() but with additional host components
    and a breakdown of project vs host.
    """
    project = Path(project).resolve()

    # Project-level
    n_tools, tool_tok, tool_tok_lazy = _tool_schema_tokens()
    n_skills, skill_tok = _skill_catalog_tokens()
    dir_tok = _directives_tokens(project)
    core_tok = _core_agent_tokens(project)

    # Host-level
    sys_tok = _estimate_system_reminder()
    n_host_skills, host_skill_tok = _estimate_host_skill_catalog()
    mcp_tok = _estimate_mcp_server_descriptions(project)
    mem_tok = _estimate_memory_block()
    profile_tok = _estimate_user_profile()

    components = {
        # Project
        "directives": dir_tok,
        "core_agent": core_tok,
        "tool_schemas": tool_tok,
        "skill_catalog": skill_tok,
        # Host
        "system_reminder": sys_tok,
        "memory_block": mem_tok,
        "user_profile": profile_tok,
        "host_skill_catalog": host_skill_tok,
        "mcp_servers": mcp_tok,
        # Internals
        "_tool_schemas_lazy": tool_tok_lazy,
        "_n_tools": n_tools,
        "_n_skills": n_skills,
        "_n_host_skills": n_host_skills,
    }

    out = summarize(components, windows)
    out["project"] = str(project)
    out["counts"] = {
        "tools": n_tools,
        "skills": n_skills,
        "host_skills": n_host_skills,
    }

    # Breakdown
    project_total = dir_tok + core_tok + tool_tok + skill_tok
    host_total = sys_tok + mem_tok + profile_tok + host_skill_tok + mcp_tok
    out["breakdown"] = {
        "project": project_total,
        "host": host_total,
        "project_pct": round(100 * project_total / (project_total + host_total), 1) if (project_total + host_total) else 0,
        "host_pct": round(100 * host_total / (project_total + host_total), 1) if (project_total + host_total) else 0,
    }

    return out
