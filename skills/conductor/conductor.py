"""Conductor — route a goal to an ordered, justified plan of capabilities.

The generalisation of the router: not "which model tier?" but "given this GOAL,
which capabilities, in which order, and what runs local?". It reads the system's
self-model (the capability registry / curator), composes a plan ordered by the
system's layers (SENSE → DECIDE → ACT → REMEMBER → GOVERN → DEPLOY), annotates
each step local vs cloud, and estimates the goal's effort.

The plan is the product — the agent (or you) executes it. Conductor never runs
anything itself. Pure stdlib + the local capability/effort modules (0 tokens).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from skills.capabilities.registry import LAYERS, REPO_ROOT, load as load_caps, curate

# Concrete invocation hint per capability (so the plan is actionable).
CAP_COMMAND = {
    "directives_audit": "python -m skills.directives_audit.cli .",
    "metrics": "python -m skills.metrics.cli .",
    "infra_advisor": "python -m skills.infra_advisor.cli auto .",
    "checkup": "python -m skills.checkup.cli .",
    "skill_finder": "python -m skills.skill_finder.cli '<task>'",
    "llm_backends": "python -m skills.llm_backends.cli audit --fresh",
    "cluster": "python -m skills.cluster.cli status --subnet",
    "auto_router": "python -m skills.auto_router.cli run '<task>'",
    "prompt_improver": "python -m skills.prompt_improver.cli '<prompt>' --json",
    "app_test": "python -m skills.app_test.cli run <spec.json> --out build",
    "ingest": "python -m skills.ingest.cli ingest <url>",
    "docgen": "python -m skills.docgen.cli draft '<topic>'",
    "mousquetaires": "python -m skills.mousquetaires.cli run <project>",
    "bootstrap": "python -m skills.bootstrap.cli <project>",
    "capabilities": "python -m skills.capabilities.cli curate '<goal>'",
}


@dataclass
class Step:
    order: int
    layer: str
    capability: str
    local: bool
    command: str
    why: str

    def to_dict(self) -> dict:
        return asdict(self)


def plan(goal: str, *, top_k: int = 6, include_effects: bool = False) -> dict:
    """Compose an ordered capability plan for a goal. 0 cloud tokens."""
    goal = (goal or "").strip()
    if not goal:
        return {"error": "empty goal"}

    caps = load_caps(preserve_paths=True)
    by_path = {c.path: c for c in caps}
    picked = [(by_path[c["path"]], c) for c in
              curate(goal, caps, top_k=top_k, include_paths=True)]

    # order by layer (the system's natural flow), then by relevance
    picked.sort(key=lambda pair: (LAYERS.index(pair[0].layer), -pair[1]["score"]))
    steps = []
    for i, (cap, c) in enumerate(picked, 1):
        name = cap.name
        command = f"see {cap.path}"
        # A matching display name in another collection does not identify a
        # built-in command. Keep that entry as a non-runnable source pointer.
        if REPO_ROOT / cap.path == REPO_ROOT / "skills" / name / "SKILL.md":
            command = CAP_COMMAND.get(name, command)
        steps.append(Step(
            order=i, layer=cap.layer, capability=name,
            local=cap.local_capable, command=command,
            why=c["why"],
        ))

    # effort: does the goal itself need cloud-grade reasoning?
    try:
        from skills.auto_router.effort import estimate
        eff = estimate(goal)
        effort = {"score": eff.score, "tier": eff.tier.name}
    except Exception:
        effort = {"score": None, "tier": "UNKNOWN"}

    serialized_steps = [s.to_dict() for s in steps]
    if include_effects:
        from skills.capabilities.effects import inspect_effects
        for step, (cap, _) in zip(serialized_steps, picked):
            # Inspect only selected capabilities, using the registry's actual
            # path rather than assuming the frontmatter name is a folder name.
            skill_path = REPO_ROOT / cap.path
            step["effects"] = inspect_effects(skill_path.parent)

    cloud_steps = [s.capability for s in steps if not s.local]
    return {
        "goal": goal,
        "effort": effort,
        "steps": serialized_steps,
        "local_first": (
            "Run every step local-first; only the reasoning inside "
            + (", ".join(cloud_steps) if cloud_steps else "—")
            + " may escalate to the cloud (auto_router decides)."),
        "cloud_tokens": 0,
    }
