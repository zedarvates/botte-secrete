"""context_profiler — how much of a small model's window is eaten *before* work?

On a modest machine the usable window is shared between the model weights' RAM and
the KV-cache, and every always-on token is paid twice (RAM + each turn). This
measures the **prefix cost** an agent carries before its first real message:

  directives    CLAUDE.md / AGENTS.md instructions (always in context)
  core_agent    the shared core-agent.md rules, if present
  tool_schemas  the MCP tool definitions injected into the agent (the hidden cost)
  skill_catalog the skills' descriptions, IF the whole catalog is injected

…then expresses it as a % of typical local windows (64k / 128k / 256k) and gives a
reduction plan (lazy tools, on-demand skill search, scoped docs). 0 cloud tokens.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_WINDOWS = {"64k": 65_536, "128k": 131_072, "256k": 262_144}
_KEPT_CORE_TOOLS = 5  # a lazy server would expose ~this many + a find_tool


def _tok(text: str) -> int:
    return max(0, len(text or "") // 4)


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
    """(#skills, tokens) if every skill's description is injected as a catalog."""
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


def summarize(components: dict, windows: dict | None = None) -> dict:
    """Pure: given per-component token counts, build the profile + reduction plan."""
    windows = windows or DEFAULT_WINDOWS
    total = sum(int(v) for k, v in components.items() if not k.startswith("_"))
    pct = {name: round(100 * total / size, 1) for name, size in windows.items()}

    ts = components.get("tool_schemas", 0)
    n_tools = components.get("_n_tools", 0)
    ts_lazy = components.get("_tool_schemas_lazy")  # real measurement, if available
    sc = components.get("skill_catalog", 0)

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
                     "how": "don't inject the catalog; use find_skills / context_budget "
                            "to load only the relevant skills per task"})
    minimal = total - sum(p["saves_tokens"] for p in plan)
    return {
        "components": {k: v for k, v in components.items() if not k.startswith("_")},
        "total_prefix_tokens": total,
        "window_pct": pct,
        "reduction_plan": plan,
        "minimal_prefix_tokens": minimal,
        "reducible_tokens": total - minimal,
        "minimal_window_pct": {name: round(100 * minimal / size, 1)
                               for name, size in windows.items()},
        "cloud_tokens": 0,
    }


def profile(project: str | Path = ".", windows: dict | None = None) -> dict:
    """Measure the always-on prefix for a project and frame it against local windows."""
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
