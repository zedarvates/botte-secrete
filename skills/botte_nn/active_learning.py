#!/usr/bin/env python3
"""Active Learning Loop — les micro-NN s'améliorent avec l'usage réel.

Pipeline :
    1. COLLECTE : chaque appel à un micro-NN logge (features, pred, outcome)
    2. AGGREGATION : les logs sont regroupés par modèle
    3. ENTRAÎNEMENT : les modèles sont ré-entraînés avec les données réelles
    4. ÉVALUATION : si l'accuracy s'améliore, les poids sont mis à jour
    5. DÉPLOIEMENT : nouveau binaire Rust + push HF + git

Usage :
    python -m skills.botte_nn.active_learning collect   # Collecte les données
    python -m skills.botte_nn.active_learning train     # Ré-entraîne les modèles
    python -m skills.botte_nn.active_learning status    # État de l'apprentissage
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np

# Repo root (parent of skills/) on the path so `skills.*` imports resolve even
# when this file is run directly, not only via `python -m`.
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from skills.botte_nn.training.train import TinyNN

try:  # Windows cp1252 consoles crash on the emoji output below.
    from skills.console_utf8 import force_utf8

    force_utf8()
except Exception:  # noqa: BLE001
    pass


# ── Stockage des logs d'apprentissage ──

DATA_DIR = Path.home() / ".cache" / "botte" / "active_learning"
MODELS_DIR = Path(__file__).resolve().parent / "models"


@dataclass
class InferenceLog:
    """Un appel à un micro-NN avec son résultat."""
    model_name: str
    features: list[float]
    predicted_class: int
    actual_class: int            # None si pas encore vérifié
    correct: Optional[bool] = None  # None si pas encore vérifié
    timestamp: float = 0.0
    latency_ms: float = 0.0


class ActiveLearning:
    """Boucle d'apprentissage actif pour les micro-NN."""

    def __init__(self):
        self.data_dir = DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs: dict[str, list[InferenceLog]] = defaultdict(list)
        self._load()

    # ── Persistance ──

    def _load(self):
        """Charge les logs depuis le disque."""
        log_file = self.data_dir / "inference_logs.jsonl"
        if not log_file.exists():
            return
        for line in log_file.read_text().splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    log = InferenceLog(**d)
                    self.logs[log.model_name].append(log)
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

    def save(self):
        """Réécrit tout le fichier (compaction; coûteux — réservé aux rares cas)."""
        log_file = self.data_dir / "inference_logs.jsonl"
        with open(log_file, "w") as f:
            for logs_list in self.logs.values():
                for log in logs_list:
                    f.write(json.dumps(asdict(log)) + "\n")

    def _append(self, log: InferenceLog):
        """Append O(1) — le chemin chaud ne doit pas réécrire tout le fichier."""
        log_file = self.data_dir / "inference_logs.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(asdict(log)) + "\n")

    # ── Collecte ──

    def log_inference(self, model_name: str, features: list[float],
                      predicted_class: int, actual_class: Optional[int] = None,
                      latency_ms: float = 0.0):
        """Enregistre un appel d'inférence pour apprentissage futur."""
        log = InferenceLog(
            model_name=model_name,
            features=features,
            predicted_class=predicted_class,
            actual_class=actual_class,
            correct=(predicted_class == actual_class) if actual_class is not None else None,
            timestamp=time.time(),
            latency_ms=latency_ms,
        )
        self.logs[model_name].append(log)
        self._append(log)

    def collect(self, verbose: bool = True) -> dict[str, int]:
        """Analyse les logs collectés et retourne les stats."""
        stats = {}
        for model_name, logs_list in self.logs.items():
            total = len(logs_list)
            with_outcome = sum(1 for l in logs_list if l.correct is not None)
            correct = sum(1 for l in logs_list if l.correct is True)
            stats[model_name] = {
                "total": total,
                "with_outcome": with_outcome,
                "correct": correct,
                "accuracy": round(correct / max(with_outcome, 1), 3),
            }
            if verbose:
                print(f"  {model_name:<20} {total:>4} logs, "
                      f"{with_outcome} validés, {correct} corrects "
                      f"({correct/max(with_outcome,1):.0%})")
        return stats

    # ── Entraînement ──

    def train(self, model_name: str, epochs: int = 2000,
              lr: float = 0.005, verbose: bool = True) -> Optional[float]:
        """Ré-entraîne un modèle avec les données réelles collectées.

        Returns:
            Nouvelle accuracy ou None si pas assez de données.
        """
        logs = self.logs.get(model_name, [])
        logs_with_outcome = [l for l in logs if l.correct is not None and l.actual_class is not None]

        if len(logs_with_outcome) < 50:
            if verbose:
                print(f"  ⏳ {model_name}: besoin de 50+ échantillons validés "
                      f"(actuel: {len(logs_with_outcome)})")
            return None

        # Vérifier que le modèle source existe
        model_path = Path(__file__).resolve().parent / "models" / f"{model_name}.json"
        if not model_path.exists():
            if verbose:
                print(f"  ❌ {model_name}: fichier modèle introuvable")
            return None

        # Charger le modèle original
        with open(model_path) as f:
            weight_data = json.load(f)

        layers = weight_data["layers"]
        activations = weight_data["activations"]
        n_features = layers[0]
        n_classes = layers[-1]

        # Filtrer les logs qui correspondent à la dimension d'entrée
        valid_logs = [l for l in logs_with_outcome if len(l.features) == n_features]
        if len(valid_logs) < 50:
            if verbose:
                print(f"  ⏳ {model_name}: {len(valid_logs)} logs avec la bonne dimension")
            return None

        # ── Split déterministe train/val (80/20) pour une évaluation honnête ──
        # Sans set de validation tenu à l'écart, on mesurerait l'accuracy sur les
        # données d'entraînement → biais d'overfit, on déploierait de pires modèles.
        rng = np.random.default_rng(42)
        order = rng.permutation(len(valid_logs))
        n_val = max(1, len(valid_logs) // 5)
        val_logs = [valid_logs[i] for i in order[:n_val]]
        train_logs = [valid_logs[i] for i in order[n_val:]]

        def _xy(sample):
            xs = np.array([l.features for l in sample], dtype=float)
            ys = np.zeros((len(sample), n_classes), dtype=float)
            for i, l in enumerate(sample):
                if l.actual_class is not None and l.actual_class < n_classes:
                    ys[i, l.actual_class] = 1.0
            return xs, ys

        X_train, y_train = _xy(train_logs)
        X_val, y_val = _xy(val_logs)

        # Baseline : accuracy de l'ancien modèle sur le set de validation,
        # d'après ses prédictions déjà loggées (predicted_class).
        old_accuracy = float(np.mean([l.predicted_class == l.actual_class for l in val_logs]))

        # Warm-start : on repart des poids existants (fine-tuning), pas de zéro.
        model = TinyNN.from_json_data(weight_data)

        if verbose:
            print(f"  🧠 {model_name}: fine-tuning sur {len(train_logs)} échantillons "
                  f"(validation: {len(val_logs)})...")
            print(f"     Accuracy actuelle (val): {old_accuracy:.1%}")

        model.train(X_train, y_train, epochs=epochs, lr=lr, verbose=verbose)

        # Évaluer sur le set de validation tenu à l'écart.
        new_accuracy = float(np.mean(model.predict(X_val).argmax(axis=1) == y_val.argmax(axis=1)))

        if verbose:
            print(f"     Nouvelle accuracy (val): {new_accuracy:.1%}")

        # On ne déploie QUE si le modèle généralise mieux sur des données non vues.
        if new_accuracy > old_accuracy:
            with open(model_path, "w") as f:
                json.dump(model.export_json(), f, indent=2)
            if verbose:
                print(f"  ✅ {model_name}: amélioré {old_accuracy:.1%} → {new_accuracy:.1%} "
                      f"(poids Rust embarqués à régénérer: active_learning rebuild)")
            return new_accuracy
        else:
            if verbose:
                print(f"  ➖ {model_name}: pas d'amélioration sur la validation "
                      f"({new_accuracy:.1%} vs {old_accuracy:.1%}) — ancien modèle conservé")
            return old_accuracy

    def train_all(self, epochs: int = 2000, verbose: bool = True) -> dict[str, float]:
        """Ré-entraîne tous les modèles qui ont assez de données."""
        results = {}
        for model_name in self.logs.keys():
            acc = self.train(model_name, epochs=epochs, verbose=verbose)
            if acc is not None:
                results[model_name] = acc
        return results

    # ── Stats ──

    def status(self) -> dict:
        """Rapport complet de l'état d'apprentissage."""
        total_logs = sum(len(logs) for logs in self.logs.values())
        total_with_outcome = sum(
            sum(1 for l in logs if l.correct is not None)
            for logs in self.logs.values()
        )

        return {
            "total_logs": total_logs,
            "with_outcome": total_with_outcome,
            "models": self.collect(verbose=False),
            "storage": str(self.data_dir / "inference_logs.jsonl"),
        }


def record_feedback(model_name: str, features: list[float], predicted_class: int,
                    actual_class: int, latency_ms: float = 0.0) -> None:
    """Append one *labelled* inference (ground truth known) for the loop to learn from.

    O(1) and load-free — the hot path must not read the whole history back. This is
    how production fills `actual_class`: callers log the real outcome (e.g. a routing
    override, or a local attempt that failed) so the micro-NN can be retrained on
    what actually happened, not synthetic data.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = InferenceLog(
        model_name=model_name, features=[float(x) for x in features],
        predicted_class=int(predicted_class), actual_class=int(actual_class),
        correct=(int(predicted_class) == int(actual_class)),
        timestamp=time.time(), latency_ms=latency_ms,
    )
    with open(DATA_DIR / "inference_logs.jsonl", "a") as f:
        f.write(json.dumps(asdict(log)) + "\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="active_learning", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="État de l'apprentissage")
    sub.add_parser("collect", help="Collecter et analyser les logs")

    s = sub.add_parser("train", help="Ré-entraîner les modèles")
    s.add_argument("--model", default=None, help="Modèle spécifique")
    s.add_argument("--epochs", type=int, default=2000)

    s = sub.add_parser("rebuild", help="Ré-entraîner + rebuild le binaire Rust")
    s.add_argument("--epochs", type=int, default=2000)

    args = p.parse_args(argv)

    al = ActiveLearning()

    if args.cmd == "status":
        s = al.status()
        print("🧠 Active Learning Status")
        print(f"  Logs totaux: {s['total_logs']}")
        print(f"  Avec verdict: {s['with_outcome']}")
        print(f"  Stockage: {s['storage']}")
        print()
        for model, stats in s["models"].items():
            print(f"  {model:<20} {stats['total']:>4} logs, "
                  f"{stats['with_outcome']} validés, "
                  f"{stats['accuracy']:.0%} accuracy")
        return 0

    elif args.cmd == "collect":
        print("📊 Collecte des logs d'inférence :")
        al.collect()
        return 0

    elif args.cmd == "train":
        if args.model:
            al.train(args.model, epochs=args.epochs)
        else:
            al.train_all(epochs=args.epochs)
        return 0

    elif args.cmd == "rebuild":
        print("🧠 Active Learning: retrain + rebuild")
        print("=" * 50)

        # 1. Entraînement
        results = al.train_all(epochs=args.epochs)
        improved = [m for m, a in results.items() if a is not None]

        # 2. Regénérer les poids embarqués
        import subprocess
        embed_script = Path(__file__).resolve().parent / "training" / "embed_weights.py"
        result = subprocess.run([sys.executable, str(embed_script)],
                                capture_output=True, text=True, cwd=str(embed_script.parent.parent))
        print(result.stdout)

        # 3. Rebuild le binaire Rust
        result = subprocess.run(["cargo", "build", "--release"],
                                capture_output=True, text=True,
                                cwd=str(embed_script.parent.parent))
        print(result.stdout[-200:] if len(result.stdout) > 200 else result.stdout)

        print(f"\n✅ Rebuild complete. Modèles améliorés: {len(improved)}/{len(results)}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
