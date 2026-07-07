"""Token Shaper — per-turn adaptive compression shaping.

Utilise l'effort_classifier (micro-NN existant) pour adapter dynamiquement
le niveau de compression à chaque tour. Basse effort → forte compression.
Haute effort → compression légère (préserver la qualité).

Stratégies :
- aggressive: 80% compression, pour tâches triviales
- normal: 50% compression, pour tâches standard
- light: 20% compression, pour tâches complexes
- none: 0% compression, pour tâches critiques
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ShapingLevel(Enum):
    AGGRESSIVE = "aggressive"   # 80% compression — tâches triviales
    NORMAL = "normal"           # 50% compression — standard
    LIGHT = "light"             # 20% compression — complexes
    NONE = "none"               # 0% compression — critiques


@dataclass
class ShapingConfig:
    """Configuration pour un niveau de shaping."""
    level: ShapingLevel
    compress_ratio: float       # 0.0-1.0, target compression
    output_tokens_target: int   # Max tokens de sortie
    skip_cache: bool            # Sauter le cache ?
    verbosity_steer: str        # Instruction de verbosité
    retain_thinking: bool       # Garder les blocs <thinking> ?


# Profils de shaping par niveau
SHAPING_PROFILES = {
    ShapingLevel.AGGRESSIVE: ShapingConfig(
        level=ShapingLevel.AGGRESSIVE,
        compress_ratio=0.20,     # 80% compression
        output_tokens_target=200,
        skip_cache=False,
        verbosity_steer="Answer in 1-2 sentences. No preamble. No explanation. Just the answer.",
        retain_thinking=False,
    ),
    ShapingLevel.NORMAL: ShapingConfig(
        level=ShapingLevel.NORMAL,
        compress_ratio=0.50,     # 50% compression
        output_tokens_target=500,
        skip_cache=False,
        verbosity_steer="Be concise. Skip preambles. Give the key information directly.",
        retain_thinking=False,
    ),
    ShapingLevel.LIGHT: ShapingConfig(
        level=ShapingLevel.LIGHT,
        compress_ratio=0.80,     # 20% compression
        output_tokens_target=1000,
        skip_cache=False,
        verbosity_steer="",
        retain_thinking=True,
    ),
    ShapingLevel.NONE: ShapingConfig(
        level=ShapingLevel.NONE,
        compress_ratio=1.0,      # 0% compression
        output_tokens_target=4000,
        skip_cache=True,
        verbosity_steer="",
        retain_thinking=True,
    ),
}


class TaskClassifier:
    """Classifie une requête pour déterminer le niveau de shaping optimal.

    Utilise l'effort_classifier micro-NN quand disponible,
    sinon utilise des heuristiques déterministes.
    """

    def __init__(self):
        self.nn_available = self._check_nn()

    def _check_nn(self) -> bool:
        """Check if the micro-NN effort classifier is available."""
        model_path = Path(__file__).parent.parent / "botte_nn" / "models" / "effort_classifier.json"
        return model_path.exists()

    def _effort_features(self, query: str, agent_type: str = "",
                         context_size: int = 0) -> list[float]:
        """Extract features for effort classification."""
        words = query.split()
        return [
            min(1.0, len(words) / 100),        # 0: query length
            min(1.0, context_size / 5000),      # 1: context size
            0.5 if "?" in query else 0.0,        # 2: is question
            0.8 if "debug" in query.lower() or "error" in query.lower() else 0.0,  # 3: debug
            0.3 if "explain" in query.lower() or "why" in query.lower() else 0.0,  # 4: explain
            0.7 if "fix" in query.lower() or "repair" in query.lower() else 0.0,   # 5: fix
            0.2 if "list" in query.lower() or "show" in query.lower() else 0.0,    # 6: list
            0.9 if "security" in query.lower() or "vuln" in query.lower() else 0.0, # 7: security
            0.5 if any(w in query.lower() for w in ["urgent", "critical", "important"]) else 0.0,  # 8: urgency
            0.3 if "?" in query and len(words) < 10 else 0.0,  # 9: simple question
        ]

    def classify(self, query: str, agent_type: str = "",
                 context_size: int = 0) -> ShapingLevel:
        """Classify a query to determine optimal shaping level."""
        features = self._effort_features(query, agent_type, context_size)

        # Try micro-NN first
        if self.nn_available:
            try:
                model_path = Path(__file__).parent.parent / "botte_nn" / "models" / "effort_classifier.json"
                result = subprocess.run(
                    [sys.executable, "-m", "skills.botte_nn.cli", "predict",
                     str(model_path), "--input"] + [str(f) for f in features],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    output = result.stdout.strip()
                    # Parse confidence from output
                    if "AGGRESSIVE" in output or "aggressive" in output.lower():
                        return ShapingLevel.AGGRESSIVE
                    elif "NORMAL" in output or "normal" in output.lower():
                        return ShapingLevel.NORMAL
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Fallback: heuristic classification
        effort_score = sum(features) / len(features)

        if effort_score > 0.7:
            return ShapingLevel.NONE      # Complexe → pas de compression
        elif effort_score > 0.5:
            return ShapingLevel.LIGHT     # Modéré → compression légère
        elif effort_score > 0.3:
            return ShapingLevel.NORMAL    # Standard → compression normale
        else:
            return ShapingLevel.AGGRESSIVE  # Simple → forte compression


class TokenShaper:
    """Per-turn adaptive token shaper.

    À chaque tour, classifie l'effort nécessaire et applique
    le niveau de shaping correspondant.
    """

    def __init__(self):
        self.classifier = TaskClassifier()
        self.shaping_history: list[dict] = []

    def shape(self, query: str, agent_type: str = "",
              context_size: int = 0) -> ShapingConfig:
        """Determine the optimal shaping for a given query."""
        level = self.classifier.classify(query, agent_type, context_size)
        config = SHAPING_PROFILES[level]

        self.shaping_history.append({
            "query": query[:50],
            "agent_type": agent_type,
            "level": level.value,
            "compress_ratio": config.compress_ratio,
            "output_target": config.output_tokens_target,
        })

        return config

    def get_verbosity_instruction(self, query: str, agent_type: str = "",
                                  context_size: int = 0) -> str:
        """Get the verbosity steering instruction for a query."""
        config = self.shape(query, agent_type, context_size)
        return config.verbosity_steer

    def get_compression_ratio(self, query: str, agent_type: str = "",
                              context_size: int = 0) -> float:
        """Get the target compression ratio for a query."""
        config = self.shape(query, agent_type, context_size)
        return config.compress_ratio

    def stats(self) -> dict:
        """Return shaping statistics."""
        if not self.shaping_history:
            return {"total_shaped": 0}

        from collections import Counter
        levels = Counter(h["level"] for h in self.shaping_history)
        total = len(self.shaping_history)
        avg_ratio = sum(h["compress_ratio"] for h in self.shaping_history) / total

        return {
            "total_shaped": total,
            "by_level": dict(levels),
            "avg_compression_ratio": round(avg_ratio, 2),
            "estimated_savings_pct": round((1 - avg_ratio) * 100, 1),
            "recent": self.shaping_history[-10:],
        }
