"""Feature schemas + featurizer — turn raw inputs into the exact vectors the
micro-NNs expect, with named, range-checked features.

Each botte_nn model was trained on a specific ordered feature vector whose meaning
lived only in a training-script docstring. That made the models orphans: nobody
could build a valid input, and `predict` happily accepted any N floats (silent
garbage-in). This module lifts those schemas into runtime data so the models are:

  * documented   — every feature has a name, range and description (`describe`)
  * validated    — `featurize` rejects unknown/missing features and clamps ranges
  * usable        — `classify` goes raw input → named features → label, in one call

Schemas are recovered verbatim from training/ (train_model.py, train_token_estimator,
train_priority_estimator, train_error_classifier). Keep them in sync if a model is
retrained with different inputs.

Deterministic, stdlib + numpy only, 0 cloud tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    lo: float
    hi: float
    desc: str


def _onehot(prefix: str, names: tuple[str, ...], desc: str) -> list[FeatureSpec]:
    return [FeatureSpec(f"{prefix}{n}", 0.0, 1.0, f"{desc}: {n} (one-hot)") for n in names]


# ── The six schemas, in model input order ──────────────────────────────────────
SCHEMAS: dict[str, list[FeatureSpec]] = {
    "binary_router": [
        FeatureSpec("complexity", 0.0, 1.0, "task complexity (e.g. effort score)"),
        FeatureSpec("budget_ratio", 0.0, 1.0, "token/cost budget remaining / total"),
        FeatureSpec("has_local_model", 0.0, 1.0, "a local backend is reachable (0/1)"),
    ],
    "effort_classifier": [
        FeatureSpec("file_size_ratio", 0.0, 1.0, "content size / 100KB"),
        FeatureSpec("token_ratio", 0.0, 1.0, "word count / 2000"),
        FeatureSpec("is_code", 0.0, 1.0, "contains code (0/1)"),
        FeatureSpec("depth_ratio", 0.0, 1.0, "directory / reasoning depth / 10"),
    ],
    "anomaly_detector": [
        FeatureSpec("log_freq", 0.0, 1.0, "log entries per minute (normalized)"),
        FeatureSpec("error_ratio", 0.0, 1.0, "fraction of error lines"),
        FeatureSpec("unique_errors", 0.0, 1.0, "distinct error types / 10"),
        FeatureSpec("avg_latency", 0.0, 1.0, "request latency / 1000ms"),
        FeatureSpec("retry_count", 0.0, 1.0, "retries / 5"),
    ],
    "token_estimator": [
        FeatureSpec("prompt_length_ratio", 0.0, 1.0, "prompt length / 8000"),
        *_onehot("tt_", ("code", "reasoning", "creative", "analysis", "search", "simple"),
                 "task type"),
        *_onehot("tm_", ("local_small", "local_medium", "cloud_small", "cloud_large"),
                 "target model"),
        FeatureSpec("complexity", 0.0, 1.0, "task complexity"),
        FeatureSpec("has_context", 0.0, 1.0, "conversation history present (0/1)"),
        FeatureSpec("expected_depth", 0.0, 1.0, "reasoning steps / 10"),
    ],
    "priority_estimator": [
        FeatureSpec("urgency", 0.0, 1.0, "urgent/critical/bug keywords"),
        FeatureSpec("dependencies_count", 0.0, 1.0, "blocking deps / 10"),
        FeatureSpec("wait_time_ratio", 0.0, 1.0, "wait time / threshold"),
        *_onehot("pt_", ("code", "fix", "review", "security", "search", "report"),
                 "task type"),
        FeatureSpec("user_tier", 0.0, 1.0, "paying user (0/1)"),
        FeatureSpec("has_deadline", 0.0, 1.0, "deadline present (0/1)"),
        FeatureSpec("complexity", 0.0, 1.0, "task complexity"),
    ],
    "error_classifier": [
        FeatureSpec("error_code_norm", 0.0, 1.0, "exit code / 255"),
        FeatureSpec("message_length_ratio", 0.0, 1.0, "message length / 2000"),
        FeatureSpec("has_traceback", 0.0, 1.0, "stack trace present (0/1)"),
        FeatureSpec("kw_syntax", 0.0, 1.0, "SyntaxError / invalid syntax / EOL"),
        FeatureSpec("kw_runtime", 0.0, 1.0, "TypeError / ValueError / KeyError"),
        FeatureSpec("kw_network", 0.0, 1.0, "ConnectionError / DNS / socket"),
        FeatureSpec("kw_permission", 0.0, 1.0, "Permission/Access denied"),
        FeatureSpec("kw_timeout", 0.0, 1.0, "timeout / TimeoutError / deadline"),
        FeatureSpec("kw_resource", 0.0, 1.0, "MemoryError / OOM / disk full"),
        FeatureSpec("line_count_ratio", 0.0, 1.0, "error lines / 100"),
        FeatureSpec("has_suggestion", 0.0, 1.0, '"did you mean?" present (0/1)'),
        FeatureSpec("exit_code_nonzero", 0.0, 1.0, "process failed (0/1)"),
    ],
}


def _clamp(x: float, lo: float, hi: float) -> float:
    x = float(x)
    return lo if x < lo else hi if x > hi else x


def feature_names(model: str) -> list[str]:
    return [s.name for s in SCHEMAS[model]]


def describe(model: str) -> str:
    specs = SCHEMAS[model]
    lines = [f"{model} — {len(specs)} features:"]
    lines += [f"  [{i:>2}] {s.name:<20} [{s.lo:g},{s.hi:g}]  {s.desc}"
              for i, s in enumerate(specs)]
    return "\n".join(lines)


def featurize(model: str, values: dict[str, float]) -> list[float]:
    """Ordered, range-clamped feature vector for `model` from a name→value dict.

    Raises ValueError on an unknown model or any missing/extra feature name — so a
    miswired caller fails loudly instead of feeding the model silent garbage.
    """
    if model not in SCHEMAS:
        raise ValueError(f"unknown model '{model}'; known: {', '.join(SCHEMAS)}")
    specs = SCHEMAS[model]
    allowed = {s.name for s in specs}
    missing = [s.name for s in specs if s.name not in values]
    extra = [k for k in values if k not in allowed]
    if missing or extra:
        raise ValueError(
            f"{model}: feature mismatch — missing={missing or '∅'} extra={extra or '∅'}")
    return [_clamp(values[s.name], s.lo, s.hi) for s in specs]


# ── Deterministic extractors: raw input → feature dict (for the text-derivable
#    models). The rest (anomaly/priority/token need queue/log/conversation context)
#    are documented via SCHEMAS so a caller with that data can featurize() safely.

_CODE_RE = re.compile(r"```|\bdef \b|\bclass \b|\bfunction\b|\bimport \b|=>|;\s*$", re.M)


def binary_router_values(complexity: float, budget_ratio: float, has_local: bool) -> dict:
    return {"complexity": complexity, "budget_ratio": budget_ratio,
            "has_local_model": 1.0 if has_local else 0.0}


def effort_classifier_values(text: str, *, is_code: bool | None = None,
                             depth: int = 0) -> dict:
    code = bool(_CODE_RE.search(text)) if is_code is None else is_code
    return {
        "file_size_ratio": min(len(text) / 102_400, 1.0),
        "token_ratio": min(len(text.split()) / 2000, 1.0),
        "is_code": 1.0 if code else 0.0,
        "depth_ratio": min(depth / 10.0, 1.0),
    }


_ERR_KW = {
    "kw_syntax": ("syntaxerror", "invalid syntax", "unexpected eof", "unexpected indent", "eol"),
    "kw_runtime": ("typeerror", "valueerror", "keyerror", "indexerror", "attributeerror", "nameerror"),
    "kw_network": ("connectionerror", "econnrefused", "dns", "socket", "httperror", "ssl", "unreachable"),
    "kw_permission": ("permission denied", "access denied", "eacces", "forbidden", "403", "not permitted"),
    "kw_timeout": ("timeout", "timed out", "timeouterror", "deadline"),
    "kw_resource": ("memoryerror", "oom", "out of memory", "disk full", "enospc", "no space left"),
}


def error_classifier_values(error_text: str, *, exit_code: int = 1) -> dict:
    low = error_text.lower()
    return {
        "error_code_norm": min(abs(exit_code), 255) / 255.0,
        "message_length_ratio": min(len(error_text) / 2000, 1.0),
        "has_traceback": 1.0 if re.search(r"traceback|stack trace|at .+\(.+:\d+\)", low) else 0.0,
        **{kw: (1.0 if any(t in low for t in terms) else 0.0) for kw, terms in _ERR_KW.items()},
        "line_count_ratio": min(error_text.count("\n") / 100.0, 1.0),
        "has_suggestion": 1.0 if "did you mean" in low else 0.0,
        "exit_code_nonzero": 1.0 if exit_code != 0 else 0.0,
    }


def classify(model: str, values: dict[str, float]) -> tuple[str, float, list[float]]:
    """Featurize + run the model → (label, confidence, probabilities).

    One call from named features to a human label. 0 cloud tokens.
    """
    from skills.botte_nn.cli import _predict_python, _MODEL_META, _MODELS_DIR

    vec = featurize(model, values)
    probs = _predict_python(str(_MODELS_DIR / f"{model}.json"), vec)
    idx = max(range(len(probs)), key=probs.__getitem__)
    labels = _MODEL_META.get(model, {}).get("labels") or [f"class_{i}" for i in range(len(probs))]
    return labels[idx], float(probs[idx]), probs
