"""Deterministic progress evaluation between consecutive loop observations."""

from __future__ import annotations

from dataclasses import dataclass, field

from skills.loop_optimizer.models import ProgressState


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    tests_passed: int = 0
    errors: int = 0
    fingerprints: dict[str, str] = field(default_factory=dict)
    information_hash: str = ""
    verified_success: bool = False

    def __post_init__(self) -> None:
        for name in ("tests_passed", "errors"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ProgressEvaluation:
    state: ProgressState
    reasons: tuple[str, ...]
    fingerprint_changed: bool
    new_information: bool


def evaluate(previous: ProgressSnapshot | None,
             current: ProgressSnapshot) -> ProgressEvaluation:
    """Classify measurable change without invoking a model."""
    if current.verified_success:
        return ProgressEvaluation(ProgressState.SOLVED, ("verification succeeded",),
                                  previous is None or previous.fingerprints != current.fingerprints,
                                  previous is None or previous.information_hash != current.information_hash)
    if previous is None:
        return ProgressEvaluation(ProgressState.PROGRESS, ("initial observation",),
                                  bool(current.fingerprints), bool(current.information_hash))

    fingerprint_changed = previous.fingerprints != current.fingerprints
    new_information = bool(current.information_hash
                           and current.information_hash != previous.information_hash)
    regressions = []
    improvements = []
    if current.errors > previous.errors:
        regressions.append(f"errors increased {previous.errors}->{current.errors}")
    elif current.errors < previous.errors:
        improvements.append(f"errors reduced {previous.errors}->{current.errors}")
    if current.tests_passed < previous.tests_passed:
        regressions.append(
            f"passing tests decreased {previous.tests_passed}->{current.tests_passed}")
    elif current.tests_passed > previous.tests_passed:
        improvements.append(
            f"passing tests increased {previous.tests_passed}->{current.tests_passed}")

    if regressions:
        return ProgressEvaluation(ProgressState.REGRESSED, tuple(regressions),
                                  fingerprint_changed, new_information)
    if improvements or fingerprint_changed or new_information:
        if fingerprint_changed:
            improvements.append("fingerprints changed")
        if new_information:
            improvements.append("new information observed")
        return ProgressEvaluation(ProgressState.PROGRESS, tuple(improvements),
                                  fingerprint_changed, new_information)
    return ProgressEvaluation(ProgressState.STALLED, ("no measurable change",),
                              False, False)
