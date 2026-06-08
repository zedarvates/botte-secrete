"""Pre-prompt loader for delegate_task.

Usage:
    from skills.loader import load_agent

    context = load_agent("porthos", project_root="/home/user/proj")
    # context = "Load core-agent.md first...\n[porthos.md content]\n\nProject: /home/user/proj"

    delegate_task(goal="Auditer le projet", context=context)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

# ── Paths ──

SKILLS_DIR = Path(__file__).parent.parent  # skills/loader/ → skills/
CORE_PROMPT = SKILLS_DIR / "core-agent.md"
MOUSQUETAIRES_PROMPTS = SKILLS_DIR / "mousquetaires" / "prompts"
CARDINAL_PROMPTS = SKILLS_DIR / "cardinal" / "prompts"

# ── Registry ──

AGENTS = {
    # Blue team
    "porthos": MOUSQUETAIRES_PROMPTS / "porthos.md",
    "dartagnan": MOUSQUETAIRES_PROMPTS / "dartagnan.md",
    "aramis": MOUSQUETAIRES_PROMPTS / "aramis.md",
    "athos": MOUSQUETAIRES_PROMPTS / "athos.md",
    # Red team
    "rochefort": CARDINAL_PROMPTS / "rochefort.md",
    "milady": CARDINAL_PROMPTS / "milady.md",
    "comte_de_wardes": CARDINAL_PROMPTS / "comte_de_wardes.md",
    "cardinal": CARDINAL_PROMPTS / "cardinal.md",
}

AGENT_DISPLAY = {
    "porthos": "🥊 Porthos",
    "dartagnan": "⚔️ d'Artagnan",
    "aramis": "📿 Aramis",
    "athos": "👑 Athos",
    "rochefort": "🗡️ Rochefort",
    "milady": "🔪 Milady",
    "comte_de_wardes": "🕯️ Comte de Wardes",
    "cardinal": "👑 Le Cardinal",
}


def load_core() -> str:
    """Charge core-agent.md."""
    if CORE_PROMPT.exists():
        return CORE_PROMPT.read_text()
    return ""


def load_delta(agent_name: str) -> str:
    """Charge le delta d'un agent spécifique.

    Args:
        agent_name: "porthos", "dartagnan", "rochefort", etc.

    Returns:
        str: contenu du pré-prompt delta

    Raises:
        ValueError: si l'agent n'existe pas
    """
    agent_name = agent_name.lower().strip()
    path = AGENTS.get(agent_name)
    if not path or not path.exists():
        raise ValueError(f"Agent '{agent_name}' not found. Available: {list(AGENTS.keys())}")
    return path.read_text()


def load_agent(
    agent_name: str,
    project_root: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> str:
    """Charge core + delta pour un agent.

    Args:
        agent_name: nom de l'agent
        project_root: chemin absolu du projet (injecté dans le contexte)
        extra_context: contexte supplémentaire (rapport précédent, etc.)

    Returns:
        str: contexte complet à passer à delegate_task(context=...)
    """
    parts = []

    # Core (always loaded first)
    core = load_core()
    if core:
        parts.append(core)
        parts.append("\n---\n")

    # Delta (agent-specific)
    delta = load_delta(agent_name)
    parts.append(delta)

    # Project context
    if project_root:
        parts.append(f"\n\n## 📁 Project Context\nProject root: `{project_root}`\n")

    # Extra context (previous reports, etc.)
    if extra_context:
        parts.append(f"\n{extra_context}")

    return "\n".join(parts)


def load_agents_batch(
    agents: list[tuple[str, str, Optional[str]]],
    project_root: Optional[str] = None,
) -> list[dict]:
    """Prépare un batch pour delegate_task(tasks=[...]).

    Args:
        agents: list of (agent_name, goal, extra_context)
        project_root: chemin projet commun

    Returns:
        list[dict]: tasks pour delegate_task(tasks=...)

    Example:
        tasks = load_agents_batch([
            ("porthos", "Auditer le projet", None),
            ("aramis", "Optimiser le projet", None),
        ], project_root="/home/user/proj")

        delegate_task(tasks=tasks)
    """
    tasks = []
    for name, goal, extra in agents:
        context = load_agent(name, project_root=project_root, extra_context=extra)
        tasks.append({
            "goal": f"{AGENT_DISPLAY.get(name, name)}: {goal}",
            "context": context,
            "toolsets": ["terminal", "file", "web", "skills"],
        })
    return tasks


def list_agents() -> list[str]:
    """Liste tous les agents disponibles."""
    return sorted(AGENTS.keys())


def agent_info(agent_name: str) -> dict:
    """Infos sur un agent."""
    path = AGENTS.get(agent_name)
    if not path or not path.exists():
        return {"error": f"Agent '{agent_name}' not found"}
    content = path.read_text()
    return {
        "name": agent_name,
        "display": AGENT_DISPLAY.get(agent_name, agent_name),
        "lines": len(content.splitlines()),
        "chars": len(content),
        "tokens_est": len(content) // 4,
    }


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m skills.loader [list|info <agent>|load <agent>]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        for a in list_agents():
            info = agent_info(a)
            print(f"  {info['display']:25s} ({info['lines']:3d}L, ~{info['tokens_est']:3d} tok)")
        print(f"\n  + core-agent.md ({len(load_core().splitlines())}L, ~{len(load_core())//4} tok)")

    elif cmd == "info" and len(sys.argv) > 2:
        info = agent_info(sys.argv[2])
        for k, v in info.items():
            print(f"  {k}: {v}")

    elif cmd == "load" and len(sys.argv) > 2:
        ctx = load_agent(sys.argv[2], project_root="/tmp/test")
        print(f"  Loaded {sys.argv[2]}: {len(ctx)} chars, ~{len(ctx)//4} tokens")
        print(f"  First 200 chars: {ctx[:200]}...")

    else:
        print(f"Unknown command: {cmd}")
