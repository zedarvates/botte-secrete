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

from skills.capabilities.registry import LAYERS, load as load_caps, curate

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


def plan(goal: str, *, top_k: int = 6) -> dict:
    """Compose an ordered capability plan for a goal. 0 cloud tokens."""
    goal = (goal or "").strip()
    if not goal:
        return {"error": "empty goal"}

    caps = load_caps()
    picked = curate(goal, caps, top_k=top_k)
    cap_layer = {c.name: c.layer for c in caps}
    cap_local = {c.name: c.local_capable for c in caps}

    # order by layer (the system's natural flow), then by relevance
    picked.sort(key=lambda c: (LAYERS.index(cap_layer.get(c["name"], "ACT")), -c["score"]))
    steps = []
    for i, c in enumerate(picked, 1):
        name = c["name"]
        steps.append(Step(
            order=i, layer=cap_layer.get(name, "ACT"), capability=name,
            local=cap_local.get(name, True),
            command=CAP_COMMAND.get(name, f"see skills/{name}/SKILL.md"),
            why=c["why"],
        ))

    # effort: does the goal itself need cloud-grade reasoning?
    try:
        from skills.auto_router.effort import estimate
        eff = estimate(goal)
        effort = {"score": eff.score, "tier": eff.tier.name}
    except Exception:
        effort = {"score": None, "tier": "UNKNOWN"}

    cloud_steps = [s.capability for s in steps if not s.local]
    return {
        "goal": goal,
        "effort": effort,
        "steps": [s.to_dict() for s in steps],
        "local_first": (
            "Run every step local-first; only the reasoning inside "
            + (", ".join(cloud_steps) if cloud_steps else "—")
            + " may escalate to the cloud (auto_router decides)."),
        "cloud_tokens": 0,
    }
