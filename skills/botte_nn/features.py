"""Feature schemas + featurizer — turn raw inputs into the exact vectors the
micro-NNs expect, with named, range-checked features.

Each botte_nn model was trained on a specific ordered feature vector whose meaning
lived only in a training-script docstring. That made the models orphans: nobody
could build a valid input, and `predict` happily accepted any N floats (silent
garbage-in). This module lifts those schemas into runtime data so the models are:

  * documented   — every feature has a name, range and description (`describe`)
  * validated    — `featurize` rejects unknown/missing features and clamps ranges
  * usable        — `classify` goes raw input → named features → label, in one call

Schemas are recovered verbatim from training/ (train_model.py,
train_error_classifier). Keep them in sync if a model is retrained with different
inputs.

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


# ── The schemas, in model input order ──────────────────────────────────────────
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
    # ── Micro-NN Belt 2.0 ──────────────────────────────────────
    "compressibility_predictor": [
        FeatureSpec("raw_length", 0.0, 1.0, "content length / 100KB"),
        FeatureSpec("content_type", 0.0, 1.0, "0=text 0.25=json 0.5=log 0.75=code 1.0=tool"),
        FeatureSpec("repetition_ratio", 0.0, 1.0, "fraction of repeated lines"),
        FeatureSpec("entropy", 0.0, 1.0, "character entropy (normalized)"),
        FeatureSpec("has_structure", 0.0, 1.0, "JSON/YAML/XML structure present"),
        FeatureSpec("json_depth", 0.0, 1.0, "JSON nesting depth / 10"),
    ],
    "context_pruning_predictor": [
        FeatureSpec("total_size", 0.0, 1.0, "total context size / 100KB"),
        FeatureSpec("num_sections", 0.0, 1.0, "number of context sections / 20"),
        FeatureSpec("section_types", 0.0, 1.0, "0=code 0.33=doc 0.66=log 1.0=mixed"),
        FeatureSpec("usage_freq", 0.0, 1.0, "historical usage frequency"),
        FeatureSpec("query_similarity", 0.0, 1.0, "semantic distance to query"),
        FeatureSpec("section_density", 0.0, 1.0, "info density (non-whitespace ratio)"),
    ],
    "skip_agent_predictor": [
        FeatureSpec("fingerprint_match", 0.0, 1.0, "code fingerprint matches cache"),
        FeatureSpec("project_hash_match", 0.0, 1.0, "project content unchanged"),
        FeatureSpec("agent_type", 0.0, 1.0, "0=audit 0.33=fix 0.66=optimize 1.0=analyze"),
        FeatureSpec("cache_history", 0.0, 1.0, "fraction of previous runs cached"),
        FeatureSpec("semantic_distance", 0.0, 1.0, "distance to previous queries"),
        FeatureSpec("criticality", 0.0, 1.0, "task criticality (0=low 1=high)"),
        FeatureSpec("recent_skip_rate", 0.0, 1.0, "fraction of recent skips that were correct"),
    ],
    "cloud_escalation_predictor": [
        FeatureSpec("effort_score", 0.0, 1.0, "effort_classifier output"),
        FeatureSpec("task_type", 0.0, 1.0, "0=audit 0.25=fix 0.5=analyze 0.75=design 1.0=research"),
        FeatureSpec("local_fail_history", 0.0, 1.0, "fraction of recent local failures"),
        FeatureSpec("criticality", 0.0, 1.0, "business criticality (0-1)"),
        FeatureSpec("budget_remaining", 0.0, 1.0, "token budget remaining / total"),
        FeatureSpec("time_pressure", 0.0, 1.0, "time remaining / total (inverted)"),
        FeatureSpec("local_model_quality", 0.0, 1.0, "estimated local model quality (0-1)"),
    ],
    "response_length_predictor": [
        FeatureSpec("query_type", 0.0, 1.0, "0=simple 0.33=explain 0.66=analyze 1.0=design"),
        FeatureSpec("agent_type", 0.0, 1.0, "0=audit 0.33=fix 0.66=report 1.0=analyze"),
        FeatureSpec("criticality", 0.0, 1.0, "task criticality"),
        FeatureSpec("history_avg_length", 0.0, 1.0, "average previous response length / 4000"),
        FeatureSpec("user_pref", 0.0, 1.0, "0=short 0.5=medium 1.0=long"),
        FeatureSpec("query_complexity", 0.0, 1.0, "effort_classifier complexity score"),
    ],
    "tool_call_predictor": [
        FeatureSpec("has_code", 0.0, 1.0, "query contains code (0/1)"),
        FeatureSpec("has_files", 0.0, 1.0, "query references file paths"),
        FeatureSpec("tool_history", 0.0, 1.0, "fraction of previous runs using tools"),
        FeatureSpec("query_type", 0.0, 1.0, "0=ask 0.33=fix 0.66=audit 1.0=deploy"),
        FeatureSpec("criticality", 0.0, 1.0, "task criticality"),
        FeatureSpec("budget_ratio", 0.0, 1.0, "token budget remaining / total"),
        FeatureSpec("time_ratio", 0.0, 1.0, "time available / required"),
    ],
    "semantic_cache_hit_predictor": [
        FeatureSpec("cache_density", 0.0, 1.0, "cache entries / max capacity"),
        FeatureSpec("query_embedding_norm", 0.0, 1.0, "norm of query embedding"),
        FeatureSpec("avg_distance", 0.0, 1.0, "avg distance to cache entries / max"),
        FeatureSpec("agent_type", 0.0, 1.0, "0=audit 0.33=fix 0.66=report 1.0=analyze"),
        FeatureSpec("pattern_frequency", 0.0, 1.0, "normalized frequency of this query pattern"),
        FeatureSpec("cache_hit_history", 0.0, 1.0, "fraction of recent queries that hit cache"),
        FeatureSpec("query_length", 0.0, 1.0, "query length / 2000 tokens"),
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
#    models). The rest (anomaly_detector needs log/queue context) are documented
#    via SCHEMAS so a caller with that data can featurize() safely.

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


# ── Micro-NN Belt 2.0 extracteurs ─────────────────────────────

def compressibility_values(text: str) -> dict:
    """Features for compressibility_predictor."""
    lines = text.split("\n")
    unique_lines = len(set(lines))
    total_lines = len(lines) or 1
    
    # Detect content type
    import json as _json
    ctype = 0.0
    if text.strip().startswith(("{", "[")):
        try:
            _json.loads(text)
            ctype = 0.25
        except _json.JSONDecodeError:
            pass
    elif any(w in text.lower() for w in ["error", "warn", "info", "debug", "trace"]):
        ctype = 0.5
    elif _CODE_RE.search(text):
        ctype = 0.75
    
    # Approximate entropy
    from collections import Counter
    char_counts = Counter(text)
    total_chars = len(text) or 1
    entropy = -sum((c/total_chars) * __import__("math").log2(c/total_chars) 
                   for c in char_counts.values()) / 8.0  # normalize to 0-1
    
    return {
        "raw_length": min(len(text) / 102_400, 1.0),
        "content_type": ctype,
        "repetition_ratio": 1.0 - (unique_lines / max(total_lines, 1)),
        "entropy": min(entropy, 1.0),
        "has_structure": 1.0 if ctype > 0 else 0.0,
        "json_depth": 0.0,  # Would need full JSON parse
    }


def context_pruning_values(total_size: float = 0.0, num_sections: int = 0,
                           section_types: str = "mixed", usage_freq: float = 0.0,
                           query_similarity: float = 0.0) -> dict:
    """Features for context_pruning_predictor."""
    stypes = {"code": 0.0, "doc": 0.33, "log": 0.66, "mixed": 1.0}
    return {
        "total_size": min(total_size / 102_400, 1.0),
        "num_sections": min(num_sections / 20.0, 1.0),
        "section_types": stypes.get(section_types, 1.0),
        "usage_freq": usage_freq,
        "query_similarity": query_similarity,
        "section_density": 0.5,  # Default
    }


def skip_agent_values(fingerprint_match: float = 0.0,
                      project_hash_match: float = 0.0,
                      agent_type: str = "audit",
                      cache_history: float = 0.0,
                      criticality: float = 0.0) -> dict:
    """Features for skip_agent_predictor."""
    atypes = {"audit": 0.0, "fix": 0.33, "optimize": 0.66, "analyze": 1.0}
    return {
        "fingerprint_match": fingerprint_match,
        "project_hash_match": project_hash_match,
        "agent_type": atypes.get(agent_type, 0.0),
        "cache_history": cache_history,
        "semantic_distance": 0.5,  # Would need embeddings
        "criticality": criticality,
        "recent_skip_rate": 0.5,  # Default
    }


def cloud_escalation_values(effort_score: float = 0.5,
                             task_type: str = "analyze",
                             local_fail_history: float = 0.0,
                             criticality: float = 0.5,
                             budget_remaining: float = 1.0) -> dict:
    """Features for cloud_escalation_predictor."""
    ttypes = {"audit": 0.0, "fix": 0.25, "analyze": 0.5, "design": 0.75, "research": 1.0}
    return {
        "effort_score": effort_score,
        "task_type": ttypes.get(task_type, 0.5),
        "local_fail_history": local_fail_history,
        "criticality": criticality,
        "budget_remaining": budget_remaining,
        "time_pressure": 0.5,
        "local_model_quality": 0.5,
    }


def response_length_values(query_type: str = "explain",
                           agent_type: str = "analyze",
                           criticality: float = 0.5,
                           user_pref: str = "medium") -> dict:
    """Features for response_length_predictor."""
    qtypes = {"simple": 0.0, "explain": 0.33, "analyze": 0.66, "design": 1.0}
    atypes = {"audit": 0.0, "fix": 0.33, "report": 0.66, "analyze": 1.0}
    uprefs = {"short": 0.0, "medium": 0.5, "long": 1.0}
    return {
        "query_type": qtypes.get(query_type, 0.33),
        "agent_type": atypes.get(agent_type, 0.33),
        "criticality": criticality,
        "history_avg_length": 0.5,
        "user_pref": uprefs.get(user_pref, 0.5),
        "query_complexity": 0.5,
    }


def tool_call_values(has_code: bool = False, has_files: bool = False,
                     query_type: str = "ask", criticality: float = 0.5,
                     budget_ratio: float = 1.0) -> dict:
    """Features for tool_call_predictor."""
    qtypes = {"ask": 0.0, "fix": 0.33, "audit": 0.66, "deploy": 1.0}
    return {
        "has_code": 1.0 if has_code else 0.0,
        "has_files": 1.0 if has_files else 0.0,
        "tool_history": 0.5,
        "query_type": qtypes.get(query_type, 0.0),
        "criticality": criticality,
        "budget_ratio": budget_ratio,
        "time_ratio": 1.0,
    }


def semantic_cache_values(cache_density: float = 0.0,
                          agent_type: str = "audit",
                          cache_hit_history: float = 0.0,
                          query_length: int = 0) -> dict:
    """Features for semantic_cache_hit_predictor."""
    atypes = {"audit": 0.0, "fix": 0.33, "report": 0.66, "analyze": 1.0}
    return {
        "cache_density": cache_density,
        "query_embedding_norm": 0.5,
        "avg_distance": 0.5,
        "agent_type": atypes.get(agent_type, 0.0),
        "pattern_frequency": 0.5,
        "cache_hit_history": cache_hit_history,
        "query_length": min(query_length / 2000, 1.0),
    }
