"""Configuration for fallow-like analysis."""

from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


class FallowConfig(BaseSettings):
    project_root: Path = Path(".")
    enable_dead_code: bool = True
    enable_duplication: bool = True
    enable_complexity: bool = True
    enable_boundaries: bool = True
    enable_feature_flags: bool = True
    enable_runtime: bool = False
    enable_hot_paths: bool = False
    enable_blast_radius: bool = True
    enable_secrets: bool = True
    complexity_threshold: int = 10
    duplication_min_lines: int = 6
    duplication_min_tokens: int = 50
    dead_code_min_confidence: float = 0.8
    hot_path_min_calls: int = 100
    blast_radius_max_depth: int = 5
    ignore_patterns: list[str] = [
        "node_modules/", ".git/", "dist/", "build/",
        "__pycache__/", ".venv/", "venv/", "*.min.js",
        "*.generated.*", ".next/", "coverage/",
    ]
    output_format: str = "text"
    output_file: Optional[Path] = None
    verbose: bool = False
    runtime_data_path: Optional[Path] = None
    history_db_path: Optional[Path] = None

    class Config:
        env_prefix = "FALLOW_"
        env_file = ".env"