"""Auto-Distiller — distillation automatique des décisions cloud → micro-NN.

Collecte les traces de décision du cloud LLM, les convertit en données
d'entraînement, et met à jour les micro-NN locaux pour réduire
progressivement les escalades cloud.

Pipeline :
1. Record — capture les décisions cloud (input, output, confiance)
2. Format — convertit en données d'entraînement (features, labels)
3. Train — entraîne/met à jour un micro-NN (via sklearn/numpy)
4. Deploy — exporte le modèle au format JSON pour le Rust inference
5. Evaluate — compare précision cloud vs local

Usage:
    python -m skills.auto_distill.cli record "input" "decision" --confidence 0.95
    python -m skills.auto_distill.cli format --output training_data.json
    python -m skills.auto_distill.cli train --model effort_classifier
    python -m skills.auto_distill.cli evaluate
    python -m skills.auto_distill.cli stats
"""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Store ───────────────────────────────────────────────────────

TRACE_STORE = Path.home() / ".botte" / "distill-traces.json"
MODEL_DIR = Path(__file__).parent.parent / "botte_nn" / "models"


@dataclass
class Trace:
    """A single cloud decision trace."""
    input_text: str
    decision: str
    features: list[float]
    confidence: float
    agent_type: str
    model_name: str
    timestamp: float = field(default_factory=time.time)
    used_for_training: bool = False


class DistillationPipeline:
    """Pipeline de distillation cloud → local."""

    def __init__(self):
        self.traces: list[Trace] = []
        self._load()

    def _load(self):
        if TRACE_STORE.exists():
            try:
                data = json.loads(TRACE_STORE.read_text())
                for t in data.get("traces", []):
                    self.traces.append(Trace(**t))
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        TRACE_STORE.parent.mkdir(parents=True, exist_ok=True)
        TRACE_STORE.write_text(json.dumps({
            "traces": [
                {"input_text": t.input_text, "decision": t.decision,
                 "features": t.features, "confidence": t.confidence,
                 "agent_type": t.agent_type, "model_name": t.model_name,
                 "timestamp": t.timestamp, "used_for_training": t.used_for_training}
                for t in self.traces
            ],
        }, indent=2))

    def _extract_features(self, text: str) -> list[float]:
        """Extract feature vector from text for training."""
        words = text.split()
        return [
            min(1.0, len(words) / 100),                   # length
            0.5 if "?" in text else 0.0,                    # is question
            0.8 if "error" in text.lower() or "fail" in text.lower() else 0.0,  # error
            0.3 if "explain" in text.lower() else 0.0,     # explain
            0.7 if "fix" in text.lower() else 0.0,         # fix
            0.2 if "list" in text.lower() else 0.0,        # list
            0.9 if "security" in text.lower() else 0.0,    # security
            0.5 if any(w in text.lower() for w in ["urgent", "critical"]) else 0.0,  # urgent
        ]

    def record(self, input_text: str, decision: str, *,
               confidence: float = 1.0, agent_type: str = "",
               model_name: str = ""):
        """Record a cloud decision trace."""
        trace = Trace(
            input_text=input_text,
            decision=decision,
            features=self._extract_features(input_text),
            confidence=confidence,
            agent_type=agent_type,
            model_name=model_name,
        )
        self.traces.append(trace)
        self._save()

        print(f"  📝 Recorded: {decision} (conf={confidence:.2f})")

    def format_training_data(self, min_confidence: float = 0.8) -> dict:
        """Convert traces to training data (features → labels)."""
        X = []
        y = []

        # Map decisions to numeric labels
        decisions = sorted(set(t.decision for t in self.traces
                               if t.confidence >= min_confidence
                               and not t.used_for_training))
        label_map = {d: i for i, d in enumerate(decisions)}

        for t in self.traces:
            if t.confidence >= min_confidence and not t.used_for_training:
                if t.decision in label_map:
                    X.append(t.features)
                    y.append(label_map[t.decision])

        return {
            "features": X,
            "labels": y,
            "label_map": label_map,
            "num_classes": len(label_map),
            "num_samples": len(X),
            "agents": list(set(t.agent_type for t in self.traces)),
        }

    def train(self, model_name: str = "auto_distilled",
              min_confidence: float = 0.8) -> Optional[Path]:
        """Train a micro-NN from cloud traces.

        Exports model weights as JSON for Rust inference.
        Uses simple logistic regression (numpy-only) to avoid sklearn dep.
        """
        data = self.format_training_data(min_confidence)

        if data["num_samples"] < 10:
            print(f"  ⚠️  Not enough samples: {data['num_samples']} < 10 needed")
            return None

        try:
            import numpy as np

            X = np.array(data["features"])
            y = np.array(data["labels"])
            num_classes = data["num_classes"]
            num_features = X.shape[1]

            # Simple logistic regression via gradient descent
            # (pure numpy — no sklearn dependency)
            weights = np.random.randn(num_features, num_classes) * 0.01
            biases = np.zeros(num_classes)

            lr = 0.01
            epochs = 100

            for epoch in range(epochs):
                # Forward
                logits = X @ weights + biases
                exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

                # Cross-entropy loss
                n = X.shape[0]
                loss = -np.sum(np.log(probs[np.arange(n), y] + 1e-9)) / n

                # Backward
                grad = probs.copy()
                grad[np.arange(n), y] -= 1
                grad /= n

                weights -= lr * (X.T @ grad)
                biases -= lr * np.sum(grad, axis=0)

            # Export model
            model_path = MODEL_DIR / f"{model_name}.json"
            MODEL_DIR.mkdir(parents=True, exist_ok=True)

            export = {
                "model": model_name,
                "architecture": "logistic_regression",
                "num_features": num_features,
                "num_classes": num_classes,
                "weights": weights.tolist(),
                "biases": biases.tolist(),
                "label_map": data["label_map"],
                "inverse_label_map": {v: k for k, v in data["label_map"].items()},
                "num_samples": data["num_samples"],
                "accuracy": "unknown",
            }

            model_path.write_text(json.dumps(export, indent=2))
            print(f"  🧠 Trained model exported to {model_path}")
            print(f"     Samples: {data['num_samples']}, Classes: {num_classes}")

            # Mark traces as used
            for t in self.traces:
                if t.confidence >= min_confidence and not t.used_for_training:
                    t.used_for_training = True
            self._save()

            return model_path

        except ImportError:
            print("  ⚠️  numpy not available — can't train")
            return None
        except Exception as e:
            print(f"  ❌ Training failed: {e}")
            return None

    def evaluate(self) -> dict:
        """Evaluate distillation progress."""
        if not self.traces:
            return {"total_traces": 0}

        total = len(self.traces)
        trained = sum(1 for t in self.traces if t.used_for_training)
        by_agent = Counter(t.agent_type for t in self.traces)
        by_decision = Counter(t.decision for t in self.traces)
        avg_confidence = sum(t.confidence for t in self.traces) / total

        # Estimate cloud escalations avoided
        avg_tokens_per_escalation = 2000
        tokens_saved = trained * avg_tokens_per_escalation

        return {
            "total_traces": total,
            "used_for_training": trained,
            "training_pct": round(trained / total * 100, 1) if total > 0 else 0,
            "avg_confidence": round(avg_confidence, 2),
            "top_agents": by_agent.most_common(5),
            "top_decisions": by_decision.most_common(5),
            "estimated_tokens_saved_by_distill": tokens_saved,
            "models_available": [p.name for p in MODEL_DIR.glob("*.json")],
        }
