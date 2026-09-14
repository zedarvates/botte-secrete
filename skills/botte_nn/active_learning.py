#!/usr/bin/env python3
"""Active Learning Loop — les micro-NN s'améliorent avec l'usage réel.

Pipeline :
    1. COLLECTE : chaque appel à un micro-NN logge (features, pred, outcome)
    2. AGGREGATION : les logs sont regroupés par modèle
    3. ENTRAÎNEMENT : un candidat apprend des verdicts du registre local
    4. ÉVALUATION : comparaison au modèle source sur un lot temporel séparé
    5. EXPORT : candidat consultatif séparé, sans remplacement ni activation

Usage :
    python -m skills.botte_nn.active_learning collect   # Collecte les données
    python -m skills.botte_nn.active_learning train --model binary_router
    python -m skills.botte_nn.active_learning status --json
    python -m skills.botte_nn.active_learning verify <feedback_id> local|cloud
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# Repo root (parent of skills/) on the path so `skills.*` imports resolve even
# when this file is run directly, not only via `python -m`.
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:  # Windows cp1252 consoles crash on the emoji output below.
    from skills.console_utf8 import force_utf8

    force_utf8()
except Exception:  # noqa: BLE001
    pass


# ── Stockage des logs d'apprentissage ──

DATA_DIR = Path.home() / ".cache" / "botte" / "active_learning"
MODELS_DIR = Path(__file__).resolve().parent / "models"


def _number(value) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _labelled(log) -> bool:
    return (log.verified is True and type(log.actual_class) is int
            and log.actual_class >= 0 and type(log.predicted_class) is int
            and log.predicted_class >= 0 and type(log.correct) is bool
            and log.correct == (log.predicted_class == log.actual_class))


def _unique_verdicts(logs):
    """Conservative sample count; local verification declarations are not attested."""
    by_input = {}
    seen_ids = set()
    conflicts = set()
    for log in sorted(logs, key=lambda item: item.timestamp):
        if not _labelled(log) or not log.outcome or log.timestamp <= 0:
            continue
        key = tuple(float(value) for value in log.features)
        if key in by_input:
            if by_input[key].actual_class != log.actual_class:
                conflicts.add(key)
            continue
        identity = log.source_observation_id or log.sample_fingerprint or log.inference_id
        if identity and identity in seen_ids:
            continue
        if identity:
            seen_ids.add(identity)
        by_input[key] = log
    return [row for key, row in by_input.items() if key not in conflicts], len(conflicts)


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class InferenceLog:
    """Un appel à un micro-NN avec son résultat."""
    model_name: str
    features: list[float]
    predicted_class: int
    actual_class: Optional[int] = None
    correct: Optional[bool] = None  # None si pas encore vérifié
    timestamp: float = 0.0
    latency_ms: float = 0.0
    verified: bool = False
    outcome: str = ""
    inference_id: str = ""
    source_observation_id: str = ""
    decision_source: str = ""
    belt_acted: bool = False
    confidence: float = 0.0
    sample_fingerprint: str = ""


class ActiveLearning:
    """Boucle d'apprentissage actif pour les micro-NN."""

    def __init__(self, *, data_dir: str | Path | None = None):
        self.data_dir = Path(DATA_DIR if data_dir is None else data_dir).expanduser()
        self.logs: dict[str, list[InferenceLog]] = defaultdict(list)
        self.candidate_paths: dict[str, Path] = {}
        self._load()

    # ── Persistance ──

    def _load(self):
        """Charge les logs depuis le disque."""
        log_file = self.data_dir / "inference_logs.jsonl"
        self.logs.clear()
        self.invalid_rows = 0
        self.ledger_sha256 = None
        try:
            raw = log_file.read_bytes()
        except FileNotFoundError:
            self.ledger_state = "missing"
            return
        except OSError:
            self.ledger_state = "unreadable"
            return
        self.ledger_sha256 = hashlib.sha256(raw).hexdigest()
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            self.ledger_state = "invalid"
            self.invalid_rows = 1
            return
        self.ledger_state = "present" if raw.strip() else "empty"
        for line in lines:
            if line.strip():
                try:
                    d = json.loads(line)
                    log = InferenceLog(**d)
                    if (not isinstance(log.model_name, str)
                            or not re.fullmatch(r"[a-z][a-z0-9_]*", log.model_name)
                            or not isinstance(log.features, list) or not log.features
                            or not all(_number(value) for value in log.features)
                            or type(log.predicted_class) is not int
                            or log.predicted_class < 0 or type(log.verified) is not bool
                            or (log.actual_class is not None
                                and (type(log.actual_class) is not int or log.actual_class < 0))
                            or (log.correct is not None and type(log.correct) is not bool)
                            or not _number(log.timestamp) or log.timestamp < 0
                            or not _number(log.latency_ms) or log.latency_ms < 0
                            or not _number(log.confidence) or not 0 <= log.confidence <= 1
                            or type(log.belt_acted) is not bool
                            or not all(isinstance(getattr(log, key), str) for key in (
                                "outcome", "inference_id", "source_observation_id",
                                "sample_fingerprint", "decision_source"))
                            or (log.verified and not _labelled(log))):
                        raise ValueError("invalid inference row")
                    self.logs[log.model_name].append(log)
                except (ValueError, KeyError, TypeError):
                    self.invalid_rows += 1
        if self.invalid_rows:
            self.ledger_state = "invalid"

    def save(self):
        """Réécrit tout le fichier (compaction; coûteux — réservé aux rares cas)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.data_dir / "inference_logs.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            for logs_list in self.logs.values():
                for log in logs_list:
                    f.write(json.dumps(asdict(log)) + "\n")

    def _append(self, log: InferenceLog):
        """Append O(1) — le chemin chaud ne doit pas réécrire tout le fichier."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.data_dir / "inference_logs.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(log)) + "\n")

    # ── Collecte ──

    def log_inference(self, model_name: str, features: list[float],
                      predicted_class: int, actual_class: Optional[int] = None,
                      latency_ms: float = 0.0, *, verified: bool = False,
                      outcome: str = ""):
        """Enregistre une observation; seuls les verdicts vérifiés sont entraînables."""
        if actual_class is not None and not verified:
            raise ValueError("actual_class requires verified=True")
        log = InferenceLog(
            model_name=model_name,
            features=features,
            predicted_class=predicted_class,
            actual_class=actual_class,
            correct=(predicted_class == actual_class) if verified else None,
            timestamp=time.time(),
            latency_ms=latency_ms,
            verified=verified,
            outcome=outcome,
        )
        self.logs[model_name].append(log)
        self._append(log)

    def collect(self, verbose: bool = True) -> dict[str, int]:
        """Analyse les logs collectés et retourne les stats."""
        stats = {}
        for model_name, logs_list in self.logs.items():
            total = len(logs_list)
            observations = sum(1 for log in logs_list if log.verified is False)
            with_outcome = sum(1 for log in logs_list if _labelled(log))
            correct = sum(1 for log in logs_list if _labelled(log) and log.correct)
            unique, conflicts = _unique_verdicts(logs_list)
            stats[model_name] = {
                "total": total,
                "observations": observations,
                "with_outcome": with_outcome,
                "correct": correct,
                "accuracy": round(correct / max(with_outcome, 1), 3),
                "unique_verified": len(unique),
                "conflicting_inputs": conflicts,
            }
            if verbose:
                print(f"  {model_name:<20} {observations:>4} observations, "
                      f"{with_outcome} validés, {correct} corrects "
                      f"({correct/max(with_outcome,1):.0%})")
        return stats

    # ── Entraînement ──

    def train(self, model_name: str, epochs: int = 2000,
              lr: float = 0.005, verbose: bool = True, *,
              output_dir: str | Path | None = None) -> Optional[float]:
        """Export an improved candidate; never replace source/embedded weights.

        Returns the exported candidate's validation accuracy, or None when
        there are too few unique verdicts or no improvement. Malformed evidence
        raises ValueError. This comparison is not a production qualification.
        """
        if not isinstance(model_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", model_name):
            raise ValueError("invalid model name")
        if type(epochs) is not int or epochs < 1 or not _number(lr) or lr <= 0:
            raise ValueError("epochs and learning rate must be positive")
        destination = Path(output_dir or self.data_dir / "candidates").expanduser().resolve()
        source_dir = MODELS_DIR.resolve()
        if destination == source_dir or source_dir in destination.parents:
            raise ValueError("candidate output must be outside the source models directory")
        self.candidate_paths.pop(model_name, None)
        self._load()
        if self.ledger_state in ("invalid", "unreadable"):
            raise ValueError(f"cannot train from {self.ledger_state} ledger")
        logs, conflicts = _unique_verdicts(self.logs.get(model_name, []))
        if len(logs) < 50:
            if verbose:
                print(f"  {model_name}: besoin de 50 verdicts uniques "
                      f"(actuel: {len(logs)}; entrées contradictoires: {conflicts})")
            return None

        # Read the source once and evaluate these exact tensors, not historical
        # predicted_class values from potentially different model versions.
        model_path = source_dir / f"{model_name}.json"
        source_bytes = model_path.read_bytes()
        weight_data = json.loads(source_bytes)
        layers = weight_data.get("layers", [])
        activations = weight_data.get("activations", [])
        weights, biases = weight_data.get("weights", []), weight_data.get("biases", [])
        if (len(layers) < 2 or any(type(size) is not int or size < 1 for size in layers)
                or not len(weights) == len(biases) == len(activations) == len(layers) - 1):
            raise ValueError("invalid source model shape")
        for index, (flat, bias, activation) in enumerate(zip(weights, biases, activations)):
            if (len(flat) != layers[index] * layers[index + 1]
                    or len(bias) != layers[index + 1]
                    or not all(_number(value) for value in [*flat, *bias])
                    or activation not in ("relu", "sigmoid", "tanh", "linear", "softmax")):
                raise ValueError("invalid source model tensors")
        n_features, n_classes = layers[0], layers[-1]
        if any(len(log.features) != n_features or log.actual_class >= n_classes for log in logs):
            raise ValueError("verdict features/classes do not match the source model")

        # Equal timestamps stay together; duplicate input vectors were removed
        # before this split. Every training record strictly predates validation.
        cutoff = logs[len(logs) * 4 // 5].timestamp
        train_logs = [log for log in logs if log.timestamp < cutoff]
        val_logs = [log for log in logs if log.timestamp >= cutoff]
        required_classes = set(range(n_classes))
        if ({log.actual_class for log in train_logs} != required_classes
                or {log.actual_class for log in val_logs} != required_classes):
            raise ValueError("temporal training and validation sets must each contain every class")

        # Diagnostics/collection remain usable with just the standard library.
        import numpy as np
        from skills.botte_nn import features
        from skills.botte_nn.training import train as trainer

        code_hashes = {
            name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for name, module in (("trainer", trainer), ("features", features))
        }
        code_hashes["active_learning"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        X_train = np.array([log.features for log in train_logs], dtype=float)
        y_train = np.eye(n_classes)[[log.actual_class for log in train_logs]]
        X_val = np.array([log.features for log in val_logs], dtype=float)
        y_val = np.array([log.actual_class for log in val_logs], dtype=int)
        model = trainer.TinyNN.from_json_data(weight_data)
        baseline = model.predict(X_val)
        if not np.isfinite(baseline).all():
            raise ValueError("non-finite source predictions")
        old_accuracy = float(np.mean(baseline.argmax(axis=1) == y_val))
        model.train(X_train, y_train, epochs=epochs, lr=lr, verbose=False)
        prediction = model.predict(X_val)
        if not np.isfinite(prediction).all():
            raise ValueError("non-finite candidate predictions")
        new_accuracy = float(np.mean(prediction.argmax(axis=1) == y_val))
        if verbose:
            print(f"  {model_name}: {len(train_logs)} entraînement / {len(val_logs)} validation; "
                  f"source {old_accuracy:.1%}, candidat {new_accuracy:.1%}")
        if new_accuracy <= old_accuracy:
            if verbose:
                print("  Aucun candidat exporté : pas d'amélioration sur ce lot.")
            return None

        def balance(rows):
            return {str(label): sum(log.actual_class == label for log in rows)
                    for label in range(n_classes)}

        candidate = model.export_json()
        candidate["trained_on"] = "local_declared_verdicts_v1"
        candidate["samples"] = len(train_logs)
        candidate["eval_accuracy"] = new_accuracy
        candidate["provenance"] = {
            "schema": "botte.micro-nn-candidate/v1",
            "model_name": model_name, "created_at": time.time(),
            "activation_allowed": False, "source_weights_replaced": False,
            "qualification": "candidate_only",
            "source_model_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_metadata": {key: value for key, value in weight_data.items()
                                if key not in ("layers", "weights", "biases", "activations")},
            "ledger_sha256": self.ledger_sha256,
            "dataset_sha256": _digest([asdict(log) for log in logs]),
            "code_sha256": code_hashes,
            "python_version": sys.version.split()[0], "numpy_version": np.__version__,
            "epochs": epochs, "learning_rate": lr,
            "split": {
                "strategy": "deduplicated_input_then_temporal_80_20",
                "cutoff_timestamp": cutoff,
                "train_count": len(train_logs), "validation_count": len(val_logs),
                "train_sha256": _digest([asdict(log) for log in train_logs]),
                "validation_sha256": _digest([asdict(log) for log in val_logs]),
                "train_classes": balance(train_logs), "validation_classes": balance(val_logs),
                "conflicting_inputs_excluded": conflicts,
            },
            "source_validation_accuracy": old_accuracy,
            "candidate_validation_accuracy": new_accuracy,
            "remaining_evidence": [
                "independent_oracle_or_reviewer_provenance", "task_heuristic_baseline",
                "independent_evaluation", "calibration", "drift_monitoring",
                "rollback_test", "intended_host_validation",
            ],
        }
        # Serialize before any output mutation. Publish within a fresh private
        # directory so repeated runs cannot replace one another's candidates.
        encoded = json.dumps(candidate, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        destination.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix=f"{model_name}-", dir=destination))
        pending, final = run_dir / "model.json.tmp", run_dir / "model.json"
        try:
            with pending.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, final)
        except OSError:
            pending.unlink(missing_ok=True)
            run_dir.rmdir()
            raise
        self.candidate_paths[model_name] = final
        if verbose:
            print(f"  Candidat consultatif exporté : {final}")
        return new_accuracy

    def train_all(self, epochs: int = 2000, verbose: bool = True, *,
                  output_dir: str | Path | None = None) -> dict[str, float]:
        """Exporte les candidats améliorés; aucune activation implicite."""
        self._load()
        if self.ledger_state in ("invalid", "unreadable"):
            raise ValueError(f"cannot train from {self.ledger_state} ledger")
        results = {}
        for model_name in list(self.logs):
            acc = self.train(model_name, epochs=epochs, verbose=verbose,
                             output_dir=output_dir)
            if acc is not None:
                results[model_name] = acc
        return results

    # ── Stats ──

    def status(self) -> dict:
        """Rapport complet de l'état d'apprentissage."""
        self._load()
        total_logs = sum(len(logs) for logs in self.logs.values())
        total_with_outcome = sum(
            sum(1 for l in logs if _labelled(l))
            for logs in self.logs.values()
        )
        total_observations = sum(
            sum(1 for log in logs if not log.verified)
            for logs in self.logs.values()
        )

        return {
            "total_logs": total_logs,
            "observations": total_observations,
            "with_outcome": total_with_outcome,
            "models": self.collect(verbose=False),
            "storage": str((self.data_dir / "inference_logs.jsonl").resolve()),
            "measurement_scope": "selected_local_ledger_only",
            "ledger_state": self.ledger_state,
            "ledger_sha256": self.ledger_sha256,
            "invalid_rows": self.invalid_rows,
            "activation_allowed": False,
        }


def record_feedback(model_name: str, features: list[float], predicted_class: int,
                    actual_class: int, latency_ms: float = 0.0, *,
                    source_observation_id: str = "", decision_source: str = "",
                    belt_acted: bool = False, confidence: float = 0.0,
                    outcome: str = "explicit_feedback",
                    sample_fingerprint: str = "") -> str:
    """Append one *labelled* inference (ground truth known) for the loop to learn from.

    O(1) and load-free — the hot path must not read the whole history back. This is
    how production fills `actual_class`: callers log an explicit override or a
    deterministic verification result so the micro-NN can be retrained on ground
    truth, not on whether a backend merely returned or failed.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    inference_id = uuid.uuid4().hex
    log = InferenceLog(
        model_name=model_name, features=[float(x) for x in features],
        predicted_class=int(predicted_class), actual_class=int(actual_class),
        correct=(int(predicted_class) == int(actual_class)),
        timestamp=time.time(), latency_ms=latency_ms, verified=True,
        outcome=str(outcome), inference_id=inference_id,
        source_observation_id=source_observation_id,
        decision_source=str(decision_source), belt_acted=bool(belt_acted),
        confidence=float(confidence), sample_fingerprint=str(sample_fingerprint),
    )
    with open(DATA_DIR / "inference_logs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(log)) + "\n")
    return inference_id


def record_observation(model_name: str, features: list[float], predicted_class: int,
                       outcome: str, latency_ms: float = 0.0, *,
                       decision_source: str = "", belt_acted: bool = False,
                       confidence: float = 0.0) -> str:
    """Append an unverified production observation; never used as a training label."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    inference_id = uuid.uuid4().hex
    log = InferenceLog(
        model_name=model_name, features=[float(x) for x in features],
        predicted_class=int(predicted_class), timestamp=time.time(),
        latency_ms=latency_ms, verified=False, outcome=str(outcome),
        inference_id=inference_id,
        decision_source=str(decision_source), belt_acted=bool(belt_acted),
        confidence=float(confidence),
    )
    with open(DATA_DIR / "inference_logs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(log)) + "\n")
    return inference_id


def record_verdict(observation_id: str, actual_class: int) -> str:
    """Verify one prior observation by id and append an auditable labelled row."""
    if actual_class not in (0, 1):
        raise ValueError("actual_class must be 0 (local) or 1 (cloud)")
    log_file = DATA_DIR / "inference_logs.jsonl"
    if not log_file.exists():
        raise ValueError(f"unknown observation_id: {observation_id}")
    source = None
    verified_sources: set[str] = set()
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = InferenceLog(**json.loads(line))
        except (json.JSONDecodeError, TypeError):
            continue
        if item.verified and item.source_observation_id:
            verified_sources.add(item.source_observation_id)
        if item.inference_id == observation_id and not item.verified:
            source = item
    if source is None or observation_id in verified_sources:
        raise ValueError(f"unknown or already-verified observation_id: {observation_id}")
    return record_feedback(
        source.model_name, source.features, source.predicted_class, actual_class,
        latency_ms=source.latency_ms, source_observation_id=observation_id,
        decision_source=source.decision_source, belt_acted=source.belt_acted,
        confidence=source.confidence, sample_fingerprint=source.sample_fingerprint,
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="active_learning", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    status_parser = sub.add_parser("status", help="Inspecter le registre local sans écriture")
    status_parser.add_argument("--json", action="store_true")
    collect_parser = sub.add_parser("collect", help="Analyser les logs existants")

    s = sub.add_parser("verify", help="Valider une observation avec un verdict réel")
    s.add_argument("feedback_id", help="Identifiant renvoyé par auto_router.run")
    s.add_argument("route", choices=("local", "cloud"), help="Route qui était correcte")

    train_parser = sub.add_parser("train", help="Exporter des candidats consultatifs séparés")
    train_parser.add_argument("--model", default=None, help="Modèle spécifique")
    train_parser.add_argument("--epochs", type=int, default=2000)
    train_parser.add_argument("--output-dir", type=Path, help="Répertoire des candidats")
    for parser in (status_parser, collect_parser, train_parser):
        parser.add_argument("--data-dir", type=Path,
                            help="Répertoire explicite contenant inference_logs.jsonl")

    s = sub.add_parser("rebuild", help="Ancienne commande désactivée (aucune promotion automatique)")
    s.add_argument("--epochs", type=int, default=2000)
    args = p.parse_args(argv)
    if args.cmd == "rebuild":
        p.error("rebuild désactivé : exporter un candidat avec train, puis le qualifier séparément")

    al = ActiveLearning(data_dir=getattr(args, "data_dir", None))
    if args.cmd == "status":
        report = al.status()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
        else:
            print("État du registre local uniquement")
            print(f"  Stockage: {report['storage']}")
            print(f"  Registre: {report['ledger_state']}; lignes invalides: {report['invalid_rows']}")
            for model, stats in report["models"].items():
                print(f"  {model}: {stats['observations']} observations, "
                      f"{stats['with_outcome']} verdicts déclarés, "
                      f"{stats['unique_verified']} exemples uniques")
            print("  Activation: non évaluée")
        return 2 if report["ledger_state"] in ("invalid", "unreadable") else 0

    if args.cmd == "collect":
        al.collect()
        if al.ledger_state in ("invalid", "unreadable"):
            print(f"Registre {al.ledger_state}; comptage incomplet.", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "verify":
        verdict_id = record_verdict(args.feedback_id, 0 if args.route == "local" else 1)
        print(f"Verdict vérifié: {args.feedback_id} → {args.route} ({verdict_id})")
        return 0

    if args.cmd == "train":
        try:
            if args.model:
                result = al.train(args.model, epochs=args.epochs, output_dir=args.output_dir)
                return 0 if result is not None else 1
            results = al.train_all(epochs=args.epochs, output_dir=args.output_dir)
            return 0 if results else 1
        except (OSError, ValueError, TypeError, ImportError) as exc:
            print(f"Entraînement refusé: {exc}", file=sys.stderr)
            return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
