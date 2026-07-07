"""NN Belt 2.0 — 7 micro-NN prédicteurs branchés dans le pipeline.

Chaque prédicteur a un rôle précis dans le pipeline de routing :

1. compressibility → décide du niveau de compression avant envoi au LLM
2. context_pruning → décide quelles sections de contexte garder
3. skip_agent → décide si l'agent peut être skipper
4. cloud_escalation → décide si la tâche monte au cloud
5. response_length → ajuste le max_tokens de sortie
6. tool_call → décide si utiliser un outil
7. semantic_cache → prédit si le cache va hit

Tous les prédicteurs retournent (label, confidence) ou None si abstention.
"""
from __future__ import annotations

from typing import Optional


# ── Confidence thresholds ──────────────────────────────────────

CONFIDENCE = 0.50  # Seuil commun — abaissé pour les modèles Belt 2.0
# Pour un softmax à 2 classes, max(probs) >= 0.5 par construction : un seuil de
# 0.50 ne fait JAMAIS abstenir un modèle binaire. Les binaires ont donc leur
# propre plancher, aligné sur la belt 1.0 (nn_belt.CONFIDENCE).
BINARY_CONFIDENCE = 0.66


def _predict(model_name: str, values: dict[str, float],
             threshold: float = CONFIDENCE) -> Optional[tuple[str, float]]:
    """Run a micro-NN prediction, abstaining if confidence < threshold."""
    try:
        from skills.botte_nn import features
        from skills.botte_nn.cli import _predict_python, _MODELS_DIR, _MODEL_META

        model_path = _MODELS_DIR / f"{model_name}.json"
        if not model_path.exists():
            return None

        vec = features.featurize(model_name, values)
        probs = _predict_python(str(model_path), vec)
        if not probs:
            return None

        from skills.botte_nn.calibration import apply_temperature, load_temperature
        probs = apply_temperature(probs, load_temperature(model_name))

        idx = max(range(len(probs)), key=probs.__getitem__)
        labels = _MODEL_META.get(model_name, {}).get("labels",
                     [f"class_{i}" for i in range(len(probs))])
        label = labels[idx]
        confidence = float(probs[idx])

        # 2 classes → le plancher binaire s'applique (sinon jamais d'abstention).
        effective = max(threshold, BINARY_CONFIDENCE) if len(probs) == 2 else threshold
        if confidence < effective:
            return None
        return label, confidence

    except Exception:
        return None


# ── Prédicteurs individuels ────────────────────────────────────

def compressibility_hint(text: str = "", content_type: str = "auto",
                         repetition_ratio: float = 0.0) -> Optional[tuple[str, float]]:
    """('none'|'delta'|'heavy', confidence). None = abstain."""
    from skills.botte_nn.features import compressibility_values
    return _predict("compressibility_predictor",
                    compressibility_values(text))


def context_pruning_hint(total_size: float = 0.0, num_sections: int = 0,
                         query_similarity: float = 0.0) -> Optional[tuple[str, float]]:
    """('keep'|'prune', confidence). None = abstain."""
    from skills.botte_nn.features import context_pruning_values
    return _predict("context_pruning_predictor",
                    context_pruning_values(total_size, num_sections, query_similarity=query_similarity))


def skip_agent_hint(fingerprint_match: float = 0.0,
                    agent_type: str = "audit",
                    cache_history: float = 0.0,
                    criticality: float = 0.0) -> Optional[tuple[str, float]]:
    """('execute'|'skip', confidence). None = abstain."""
    from skills.botte_nn.features import skip_agent_values
    return _predict("skip_agent_predictor",
                    skip_agent_values(fingerprint_match, agent_type=agent_type,
                                      cache_history=cache_history, criticality=criticality))


def cloud_escalation_hint(effort_score: float = 0.5,
                          task_type: str = "analyze",
                          local_fail_history: float = 0.0,
                          criticality: float = 0.5) -> Optional[tuple[str, float]]:
    """('local_small'|'local_big'|'cloud', confidence). None = abstain."""
    from skills.botte_nn.features import cloud_escalation_values
    return _predict("cloud_escalation_predictor",
                    cloud_escalation_values(effort_score, task_type,
                                            local_fail_history, criticality))


def response_length_hint(query_type: str = "explain",
                         agent_type: str = "analyze",
                         criticality: float = 0.5,
                         user_pref: str = "medium") -> Optional[tuple[str, float]]:
    """('short'|'medium'|'long', confidence). None = abstain."""
    from skills.botte_nn.features import response_length_values
    return _predict("response_length_predictor",
                    response_length_values(query_type, agent_type, criticality, user_pref))


def tool_call_hint(has_code: bool = False, has_files: bool = False,
                   query_type: str = "ask",
                   criticality: float = 0.5) -> Optional[tuple[str, float]]:
    """('llm_only'|'use_tool', confidence). None = abstain."""
    from skills.botte_nn.features import tool_call_values
    return _predict("tool_call_predictor",
                    tool_call_values(has_code, has_files, query_type, criticality))


def semantic_cache_hint(cache_density: float = 0.0,
                        agent_type: str = "audit",
                        cache_hit_history: float = 0.0,
                        query_length: int = 0) -> Optional[tuple[str, float]]:
    """('miss'|'hit', confidence). None = abstain."""
    from skills.botte_nn.features import semantic_cache_values
    return _predict("semantic_cache_hit_predictor",
                    semantic_cache_values(cache_density, agent_type, cache_hit_history, query_length))


# ── Composite hint — tous les prédicteurs en un appel ──────────

def full_belt_hint(text: str = "", agent_type: str = "audit",
                   task_type: str = "analyze", criticality: float = 0.5,
                   has_code: bool = False) -> dict:
    """Run all 7 predictors and return their hints."""
    return {
        "compressibility": compressibility_hint(text),
        "context_pruning": context_pruning_hint(query_similarity=0.5),
        "skip_agent": skip_agent_hint(agent_type=agent_type, criticality=criticality),
        "cloud_escalation": cloud_escalation_hint(task_type=task_type, criticality=criticality),
        "response_length": response_length_hint(agent_type=agent_type, criticality=criticality),
        "tool_call": tool_call_hint(has_code=has_code, query_type=task_type, criticality=criticality),
        "semantic_cache": semantic_cache_hint(agent_type=agent_type),
    }
