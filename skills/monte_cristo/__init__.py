"""Monte Cristo — independent strategic outsider and report contract."""

from skills.monte_cristo.contract import (
    ReportValidationError,
    assert_valid_report,
    new_report,
    validate_report,
)
from skills.monte_cristo.routing import (
    TriggerContext,
    TriggerDecision,
    evaluate_trigger,
    should_invoke,
)
from skills.monte_cristo.evaluation import (
    TriggerBenchmarkResult,
    TriggerEvalCase,
    automatic_activation_allowed,
    benchmark,
    load_cases,
)

__all__ = [
    "ReportValidationError",
    "assert_valid_report",
    "new_report",
    "validate_report",
    "TriggerContext",
    "TriggerDecision",
    "evaluate_trigger",
    "should_invoke",
    "TriggerBenchmarkResult",
    "TriggerEvalCase",
    "automatic_activation_allowed",
    "benchmark",
    "load_cases",
]

__version__ = "0.1.0"
