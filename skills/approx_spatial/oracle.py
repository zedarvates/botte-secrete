"""Deterministic decision semantics for ApproxSpatial evidence.

The oracle intentionally separates measurement from proposition evaluation:
an interval/set can support YES, NO, UNKNOWN, or CONFLICT without inventing a
point estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class Verdict(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, order=True)
class Interval:
    low: float
    high: float

    def __post_init__(self) -> None:
        if isinstance(self.low, bool) or isinstance(self.high, bool):
            raise ValueError("interval bounds must be finite numbers")
        if not math.isfinite(float(self.low)) or not math.isfinite(float(self.high)):
            raise ValueError("interval bounds must be finite numbers")
        if self.low > self.high:
            raise ValueError("interval low must not exceed high")

    def to_list(self) -> list[float]:
        return [float(self.low), float(self.high)]


@dataclass(frozen=True)
class SpatialEvidence:
    admissible: tuple[Interval, ...] | None
    excluded: tuple[Interval, ...] = ()
    guard_failures: tuple[str, ...] = ()
    method: str = "fixture"

    @classmethod
    def from_mapping(cls, item: Mapping[str, object]) -> "SpatialEvidence":
        raw_admissible = item.get("admissible_m")
        admissible = None if raw_admissible is None else _intervals(raw_admissible)
        return cls(
            admissible=admissible,
            excluded=_intervals(item.get("excluded_m", [])),
            guard_failures=tuple(str(x) for x in item.get("guard_failures", [])),
            method=str(item.get("method", "fixture")),
        )

    def to_dict(self) -> dict:
        return {
            "admissible_m": None if self.admissible is None else [
                interval.to_list() for interval in self.admissible
            ],
            "excluded_m": [interval.to_list() for interval in self.excluded],
            "guard_failures": list(self.guard_failures),
            "method": self.method,
        }


def _intervals(values: object) -> tuple[Interval, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError("interval collection must be iterable")
    out = []
    for pair in values:
        if isinstance(pair, (str, bytes)) or not isinstance(pair, Iterable):
            raise ValueError("interval must contain low/high bounds")
        bounds = list(pair)
        if len(bounds) != 2:
            raise ValueError("interval must contain exactly two bounds")
        out.append(Interval(bounds[0], bounds[1]))
    return tuple(sorted(out))


def evaluate_less_than(evidence: SpatialEvidence, threshold: float) -> Verdict:
    """Evaluate the proposition ``distance < threshold``.

    Guard failure or absent measurement means UNKNOWN. An explicitly empty
    admissible set means contradictory constraints (CONFLICT).
    """
    if isinstance(threshold, bool) or not math.isfinite(float(threshold)):
        raise ValueError("threshold must be a finite number")
    if evidence.guard_failures or evidence.admissible is None:
        return Verdict.UNKNOWN
    if not evidence.admissible:
        return Verdict.CONFLICT
    if all(interval.high < threshold for interval in evidence.admissible):
        return Verdict.YES
    if all(interval.low >= threshold for interval in evidence.admissible):
        return Verdict.NO
    return Verdict.UNKNOWN
