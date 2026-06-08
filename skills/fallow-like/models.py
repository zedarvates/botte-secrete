"""Pydantic models for fallow-like analysis results."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class Finding(BaseModel):
    """A single analysis finding."""
    rule_id: str = ""
    severity: Severity = Severity.INFO
    message: str = ""
    file: str = ""
    line: int = 0
    column: int = 0
    end_line: int = 0
    snippet: str = ""
    confidence: float = 1.0
    tags: list[str] = Field(default_factory=list)
    fix_hint: str = ""


class DeadCodeFinding(Finding):
    symbol_type: str = ""
    symbol_name: str = ""
    references_found: int = 0


class DuplicationFinding(Finding):
    duplicate_file: str = ""
    duplicate_line: int = 0
    duplicate_end_line: int = 0
    lines_count: int = 0
    tokens_count: int = 0


class ComplexityFinding(Finding):
    function_name: str = ""
    complexity: int = 0
    halstead_volume: float = 0.0
    nesting_depth: int = 0
    lines_of_code: int = 0


class BoundaryViolation(Finding):
    source_layer: str = ""
    target_layer: str = ""
    violation_type: str = ""
    allowed: bool = False


class FeatureFlagFinding(Finding):
    flag_name: str = ""
    flag_type: str = ""
    locations: list[str] = Field(default_factory=list)
    stale: bool = False


class HotPathFinding(Finding):
    path: str = ""
    call_count: int = 0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    importance_score: float = 0.0


class BlastRadiusFinding(Finding):
    changed_symbol: str = ""
    direct_dependents: int = 0
    transitive_dependents: int = 0
    risk_level: str = ""


class SecretFinding(Finding):
    secret_type: str = ""
    pattern_matched: str = ""
    entropy: float = 0.0


class HealthScore(BaseModel):
    score: int = Field(ge=0, le=100, default=100)
    grade: str = "C"
    deductions: int = 0
    breakdown: dict[str, int] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ProjectStats(BaseModel):
    total_files: int = 0
    total_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    layers: dict[str, int] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    project_root: str = ""
    stats: ProjectStats = Field(default_factory=ProjectStats)
    health: HealthScore = Field(default_factory=HealthScore)
    findings: list = Field(default_factory=list)
    dead_code: list = Field(default_factory=list)
    duplication: list = Field(default_factory=list)
    complexity: list = Field(default_factory=list)
    boundaries: list = Field(default_factory=list)
    feature_flags: list = Field(default_factory=list)
    hot_paths: list = Field(default_factory=list)
    blast_radius: list = Field(default_factory=list)
    secrets: list = Field(default_factory=list)
    trends: dict = Field(default_factory=dict)
    duration_seconds: float = 0.0
