"""JSON output formatter."""

from __future__ import annotations
import json
from skills.fallow_like.models import AnalysisResult


def format(result: AnalysisResult) -> str:
    return json.dumps(result.model_dump(), indent=2, default=str)
