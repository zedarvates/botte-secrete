"""Cheap deterministic spatial reasoning primitives for Botte R&D."""

from .oracle import Interval, SpatialEvidence, Verdict, evaluate_less_than

__all__ = ["Interval", "SpatialEvidence", "Verdict", "evaluate_less_than"]
