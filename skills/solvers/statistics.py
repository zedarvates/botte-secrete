"""Bounded descriptive statistics for supplied data, with no I/O or model call.

Numbers use IEEE-754 binary64 inputs/outputs. Integers outside the exactly
representable range [-2**53, 2**53] are rejected. Exact input ratios are used
for summation and percentile interpolation before one final float conversion.
Unrepresentable requested results fail; values are never silently discarded.
"""

from __future__ import annotations

from fractions import Fraction
import math
import statistics

MAX_VALUES = 10_000
MAX_PERCENTILES = 16
OPERATIONS = (
    "count", "sum", "min", "max", "mean", "median",
    "variance_population", "variance_sample", "stdev_population", "stdev_sample",
)
DEFAULT_OPERATIONS = ("count", "sum", "min", "max", "mean", "median")
MAX_OPERATIONS = len(OPERATIONS)


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be an integer or float, not bool or text")
    if type(value) is int and abs(value) > 2**53:
        raise ValueError(f"{label} integer exceeds the exact binary64 range")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _finite_result(value: object, operation: str) -> float:
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{operation} result is not representable as binary64") from exc
    if not math.isfinite(number):
        raise ValueError(f"{operation} result is not representable as binary64")
    return number


def _stdev(numbers: list[float], sample: bool) -> float:
    """Scale an exact variance before sqrt to avoid intermediate overflow.

    This also retains subnormal standard deviations when their variance would
    underflow binary64. It uses only public stdlib APIs on Python 3.10+.
    """
    ratios = [Fraction(number) for number in numbers]
    center = sum(ratios, Fraction()) / len(ratios)
    variance = sum(((number - center)**2 for number in ratios), Fraction())
    variance /= len(ratios) - int(sample)
    if not variance:
        return 0.0
    exponent = variance.numerator.bit_length() - variance.denominator.bit_length()
    exponent -= exponent % 2
    scaled = variance / Fraction(2)**exponent
    return math.ldexp(math.sqrt(float(scaled)), exponent // 2)


def compute_statistics(values: list, operations: list[str] | None = None,
                       percentiles: list | None = None,
                       missing: str = "reject") -> dict:
    """Compute requested metrics and type-7 linear percentiles (0 through 100).

    ``missing='omit'`` omits only explicit None entries and reports their count.
    Sample variance/stdev require at least two retained observations. Empty or
    duplicate operation lists and duplicate percentiles are invalid. Errors use
    ValueError; successful output is strict JSON data with finite numbers only.
    """
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
        raise ValueError(f"values must contain 1 through {MAX_VALUES} entries")
    if missing not in ("reject", "omit"):
        raise ValueError("missing must be 'reject' or 'omit'")

    selected = list(DEFAULT_OPERATIONS) if operations is None else operations
    if (not isinstance(selected, list)
            or not 1 <= len(selected) <= MAX_OPERATIONS
            or any(type(item) is not str or item not in OPERATIONS for item in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("operations must be a nonempty unique list of supported names")

    requested = [] if percentiles is None else percentiles
    if not isinstance(requested, list) or len(requested) > MAX_PERCENTILES:
        raise ValueError(f"percentiles must be a list of at most {MAX_PERCENTILES} values")
    points = [_number(value, "percentile") for value in requested]
    if any(not 0 <= value <= 100 for value in points) or len(set(points)) != len(points):
        raise ValueError("percentiles must be unique numbers from 0 through 100")

    numbers, omitted = [], 0
    for index, value in enumerate(values):
        if value is None and missing == "omit":
            omitted += 1
        else:
            numbers.append(_number(value, f"values[{index}]"))
    if not numbers:
        raise ValueError("at least one retained numeric value is required")
    if len(numbers) < 2 and {"variance_sample", "stdev_sample"}.intersection(selected):
        raise ValueError("sample variance and stdev require at least two values")

    ordered = sorted(numbers)
    count = len(numbers)
    results = {}
    for operation in selected:
        try:
            if operation == "count":
                results[operation] = count
                continue
            if operation == "sum":
                value = sum((Fraction(number) for number in numbers), Fraction())
            elif operation == "min":
                value = ordered[0]
            elif operation == "max":
                value = ordered[-1]
            elif operation == "mean":
                value = statistics.mean(numbers)
            elif operation == "median":
                middle = count // 2
                value = (ordered[middle] if count % 2
                         else statistics.mean(ordered[middle - 1:middle + 1]))
            elif operation == "variance_population":
                value = statistics.pvariance(numbers)
            elif operation == "variance_sample":
                value = statistics.variance(numbers)
            elif operation == "stdev_population":
                value = _stdev(numbers, sample=False)
            else:
                value = _stdev(numbers, sample=True)
            results[operation] = _finite_result(value, operation)
        except (OverflowError, statistics.StatisticsError) as exc:
            raise ValueError(f"{operation} result is not representable as binary64") from exc

    quantiles = []
    for percentile in points:
        position = (count - 1) * Fraction(percentile) / 100
        lower = position.numerator // position.denominator
        upper = min(lower + 1, count - 1)
        weight = position - lower
        value = Fraction(ordered[lower]) * (1 - weight) + Fraction(ordered[upper]) * weight
        quantiles.append({"percentile": percentile,
                          "value": _finite_result(value, "percentile")})

    return {
        "schema": "botte.statistics/v1",
        "status": "computed",
        "input": {"count": len(values), "used": count, "omitted": omitted,
                  "missing_policy": missing},
        "results": results,
        "percentiles": quantiles,
        "methods": {"numeric": "binary64", "percentiles": "linear_type7",
                    "variance_population": "ddof=0", "variance_sample": "ddof=1"},
        "execution": {"model_calls": 0, "network_calls": 0},
    }
