"""Named agent-role policy for Factory Assurance.

This module does not execute agents. It describes which Botte Secrete agents may
produce, critique, orchestrate, or independently judge evidence so a run cannot
silently collapse builder and verifier authority into one identity.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class AgentRole:
    name: str
    team: str
    functions: tuple[str, ...]
    may_build: bool = False
    may_critique: bool = False
    may_judge: bool = False
    may_orchestrate: bool = False
    strategic_only: bool = False

    def to_dict(self) -> dict:
        value = asdict(self)
        value["functions"] = list(self.functions)
        return value


# These are governance roles, not execution credentials. Being listed here does
# not grant permission to run tools, mutate repositories, merge, or deploy.
AGENT_ROLES: dict[str, AgentRole] = {
    "conductor": AgentRole(
        "conductor", "orchestration", ("compose_plan", "order_capabilities", "gate_steps"),
        may_orchestrate=True,
    ),
    "porthos": AgentRole(
        "porthos", "blue", ("audit", "collect_findings"), may_build=False, may_critique=True,
    ),
    "dartagnan": AgentRole(
        "dartagnan", "blue", ("implement_fix",), may_build=True,
    ),
    "aramis": AgentRole(
        "aramis", "blue", ("optimize",), may_build=True,
    ),
    "athos": AgentRole(
        "athos", "blue", ("coordinate_blue", "consolidate_blue"), may_orchestrate=True,
    ),
    "rochefort": AgentRole(
        "rochefort", "red", ("counter_audit",), may_critique=True, may_judge=True,
    ),
    "milady": AgentRole(
        "milady", "red", ("counter_developer", "regression_hunt"), may_critique=True, may_judge=True,
    ),
    "comte_de_wardes": AgentRole(
        "comte_de_wardes", "red", ("counter_optimize",), may_critique=True, may_judge=True,
    ),
    "cardinal": AgentRole(
        "cardinal", "red", ("coordinate_red", "synthesize_adversarial_verdict"),
        may_critique=True, may_judge=True, may_orchestrate=True,
    ),
    "monte_cristo": AgentRole(
        "monte_cristo", "strategic", ("challenge_shared_assumptions", "compare_directions"),
        may_critique=True, strategic_only=True,
    ),
    "gauntlet": AgentRole(
        "gauntlet", "assurance", ("verify_evidence", "verify_regressions", "verify_compliance"),
        may_critique=True, may_judge=True,
    ),
}


def get_role(name: str) -> AgentRole | None:
    return AGENT_ROLES.get(str(name).strip().lower())


def validate_assignment(*, builder: str, judge: str, orchestrator: str | None = None) -> list[str]:
    """Return deterministic blockers for a named factory-role assignment.

    Unknown identities remain allowed because external/local workers may be used;
    they are still subject to the core builder != judge rule. Known identities
    receive the stronger role-policy checks below.
    """
    blockers: list[str] = []
    b = str(builder or "").strip().lower()
    j = str(judge or "").strip().lower()
    o = str(orchestrator or "").strip().lower()

    if b and j and b == j:
        blockers.append("builder and judge must be independent")

    builder_role = get_role(b)
    judge_role = get_role(j)
    orchestrator_role = get_role(o) if o else None

    if builder_role and not builder_role.may_build:
        blockers.append(f"agent {b} is not a builder role")
    if judge_role and not judge_role.may_judge:
        blockers.append(f"agent {j} is not an independent judge role")
    if orchestrator_role and not orchestrator_role.may_orchestrate:
        blockers.append(f"agent {o} is not an orchestrator role")

    # Strategic challenge is deliberately outside the normal build/judge path.
    if builder_role and builder_role.strategic_only:
        blockers.append(f"strategic agent {b} cannot build the candidate")
    if judge_role and judge_role.strategic_only:
        blockers.append(f"strategic agent {j} cannot serve as the routine evidence judge")

    return blockers


def public_roster() -> list[dict]:
    """Return a stable public-safe role roster for docs/dashboard use."""
    return [AGENT_ROLES[name].to_dict() for name in sorted(AGENT_ROLES)]
