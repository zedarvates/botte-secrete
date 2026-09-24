#!/usr/bin/env python3
"""Deterministic tests for named Factory Assurance agent roles."""

from __future__ import annotations

from .roles import AGENT_ROLES, public_roster, validate_assignment


def _ok(label: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    state[0 if condition else 1] += 1


def main() -> int:
    state = [0, 0]

    _ok("d'Artagnan is a builder", AGENT_ROLES["dartagnan"].may_build, state)
    _ok("Rochefort is an independent judge", AGENT_ROLES["rochefort"].may_judge, state)
    _ok("Conductor orchestrates but does not judge", AGENT_ROLES["conductor"].may_orchestrate and not AGENT_ROLES["conductor"].may_judge, state)
    _ok("Monte Cristo stays strategic-only", AGENT_ROLES["monte_cristo"].strategic_only and not AGENT_ROLES["monte_cristo"].may_build, state)
    _ok("Blue builder + red judge is accepted", not validate_assignment(builder="dartagnan", judge="rochefort", orchestrator="conductor"), state)
    _ok("Blue builder cannot self-judge", bool(validate_assignment(builder="dartagnan", judge="dartagnan")), state)
    _ok("Conductor cannot be used as routine judge", any("judge role" in b for b in validate_assignment(builder="dartagnan", judge="conductor")), state)
    _ok("Monte Cristo cannot become routine builder", any("builder" in b for b in validate_assignment(builder="monte_cristo", judge="gauntlet")), state)
    _ok("unknown external workers remain possible", not validate_assignment(builder="local-worker-7", judge="external-reviewer-2"), state)

    roster = public_roster()
    _ok("public roster exposes no execution credentials", all("token" not in str(item).lower() and "secret" not in str(item).lower() for item in roster), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
