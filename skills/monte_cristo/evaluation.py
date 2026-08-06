"""Deterministic trigger benchmark and fail-closed activation gate."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from skills.monte_cristo.routing import TriggerContext, evaluate_trigger


DEFAULT_DATASET = Path(__file__).with_name("eval_cases.jsonl")
DATASET_VERSION = "monte-cristo-trigger-v1"
MIN_CASES = 40
MIN_POSITIVE_CASES = 16
MIN_NEGATIVE_CASES = 16


@dataclass(frozen=True)
class TriggerEvalCase:
    id: str
    language: str
    query: str
    expected: bool
    kind: str
    context: TriggerContext = TriggerContext()


@dataclass(frozen=True)
class TriggerBenchmarkResult:
    dataset_version: str
    total: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    routine_false_positives: int
    precision: float
    recall: float
    specificity: float
    accuracy: float
    p95_latency_ms: float
    false_positive_ids: tuple[str, ...]
    false_negative_ids: tuple[str, ...]

    @property
    def positive_cases(self) -> int:
        return self.true_positives + self.false_negatives

    @property
    def negative_cases(self) -> int:
        return self.true_negatives + self.false_positives

    def meets_activation_gate(self) -> bool:
        """Require broad coverage and zero unsafe over-triggering."""
        return (
            self.total >= MIN_CASES
            and self.positive_cases >= MIN_POSITIVE_CASES
            and self.negative_cases >= MIN_NEGATIVE_CASES
            and self.false_positives == 0
            and self.routine_false_positives == 0
            and self.precision >= 0.95
            and self.recall >= 0.90
            and self.accuracy >= 0.95
            and self.p95_latency_ms < 5.0
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["false_positive_ids"] = list(self.false_positive_ids)
        data["false_negative_ids"] = list(self.false_negative_ids)
        data["activation_allowed"] = self.meets_activation_gate()
        return data


def _context(value: object, case_id: str) -> TriggerContext:
    if not isinstance(value, dict):
        raise ValueError(f"{case_id}: context must be an object")
    allowed = {
        "material_consequence", "blue_red_stalled", "inherited_frame",
        "routine_scope",
    }
    unexpected = set(value) - allowed
    if unexpected:
        raise ValueError(f"{case_id}: unexpected context keys {sorted(unexpected)}")
    if any(not isinstance(item, bool) for item in value.values()):
        raise ValueError(f"{case_id}: context values must be booleans")
    return TriggerContext(**value)


def load_cases(path: str | Path = DEFAULT_DATASET) -> list[TriggerEvalCase]:
    """Load the strict, append-friendly JSONL evaluation corpus."""
    dataset_path = Path(path)
    cases: list[TriggerEvalCase] = []
    seen: set[str] = set()
    required = {"id", "language", "query", "expected", "kind", "context"}
    for line_number, line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError(f"line {line_number}: expected exactly {sorted(required)}")
        case_id = item["id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"line {line_number}: id must be a non-empty string")
        if case_id in seen:
            raise ValueError(f"line {line_number}: duplicate id {case_id!r}")
        seen.add(case_id)
        if item["language"] not in {"fr", "en"}:
            raise ValueError(f"{case_id}: unsupported language")
        if item["kind"] not in {"strategic", "routine", "ambiguous", "literary"}:
            raise ValueError(f"{case_id}: unsupported kind")
        if not isinstance(item["query"], str) or not item["query"].strip():
            raise ValueError(f"{case_id}: query must be a non-empty string")
        if not isinstance(item["expected"], bool):
            raise ValueError(f"{case_id}: expected must be boolean")
        cases.append(TriggerEvalCase(
            id=case_id,
            language=item["language"],
            query=item["query"],
            expected=item["expected"],
            kind=item["kind"],
            context=_context(item["context"], case_id),
        ))
    if not cases:
        raise ValueError("at least one evaluation case is required")
    return cases


def benchmark(cases: Sequence[TriggerEvalCase]) -> TriggerBenchmarkResult:
    """Measure trigger quality and latency without running any model."""
    if not cases:
        raise ValueError("at least one evaluation case is required")
    tp = tn = fp = fn = routine_fp = 0
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    latencies: list[float] = []
    for case in cases:
        started = time.perf_counter()
        decision = evaluate_trigger(case.query, case.context)
        latencies.append((time.perf_counter() - started) * 1000)
        if decision.invoke and case.expected:
            tp += 1
        elif not decision.invoke and not case.expected:
            tn += 1
        elif decision.invoke:
            fp += 1
            false_positive_ids.append(case.id)
            routine_fp += int(case.kind in {"routine", "literary"})
        else:
            fn += 1
            false_negative_ids.append(case.id)

    total = len(cases)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    ordered = sorted(latencies)
    p95_index = min(total - 1, max(0, int(total * 0.95 + 0.999999) - 1))
    return TriggerBenchmarkResult(
        dataset_version=DATASET_VERSION,
        total=total,
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
        routine_false_positives=routine_fp,
        precision=precision,
        recall=recall,
        specificity=specificity,
        accuracy=(tp + tn) / total,
        p95_latency_ms=ordered[p95_index],
        false_positive_ids=tuple(false_positive_ids),
        false_negative_ids=tuple(false_negative_ids),
    )


def automatic_activation_allowed(result: TriggerBenchmarkResult | None) -> bool:
    """Missing or insufficient evaluation data always fails closed."""
    return result is not None and result.meets_activation_gate()
