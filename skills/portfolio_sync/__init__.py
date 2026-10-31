"""Read-only portfolio registry validation and drift comparison."""

from .core import (
    PortfolioError,
    compare_github_inventory,
    iter_projects,
    load_observed_inventory,
    load_registry,
    summarize_registry,
    validate_registry,
)

__all__ = [
    "PortfolioError",
    "compare_github_inventory",
    "iter_projects",
    "load_observed_inventory",
    "load_registry",
    "summarize_registry",
    "validate_registry",
]
