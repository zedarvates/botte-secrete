"""nn_audit — is each micro-NN grounded in reality, or a synthetic copy of a rule?

A learned component only earns its place if it's trained on **real data a rule
can't capture**. A net trained on `np.random` + hand-coded labels just approximates
a deterministic function we already wrote — strictly worse than calling the rule
(adds error + opacity, learns nothing). This tool scans `skills/botte_nn` and, per
model, reports:

  data_source     real | synthetic | unknown   (from the training script's content)
  has_provenance  does the model file record trained_on / eval_accuracy / data?
  has_test_guard  does a test assert a specific real-world output for it?
  verdict         grounded | synthetic (mimics a rule) | unknown

0 cloud tokens — pure file inspection. Reproducible; wireable into /checkup.
"""

from __future__ import annotations

import json
from pathlib import Path

# Keys that record where a model came from (vs pure architecture).
PROVENANCE_KEYS = {
    "trained_on", "data", "data_source", "eval_accuracy", "accuracy",
    "held_out_accuracy", "provenance", "samples", "trained_at", "eval", "dataset",
}
# Markers in a training script that mean it learns from REAL data.
REAL_MARKERS = ("distill", "labelled", "labeled", "corpus", ".jsonl", "logged",
                "ground truth", "ground_truth", "real error", "real-world", "real data")
# Markers that mean the data is synthesised.
SYNTH_MARKERS = ("np.random", "numpy.random", "random.rand", "random.randint",
                 "random.choice", "synthetic")


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _production_files(scan_root: Path, botte_nn: Path) -> dict:
    """Map .py file → text for code that could *consume* a model — i.e. anything
    under scan_root except tests, and except botte_nn's own infra (training/,
    models/, cli.py registry, features.py schema, the nn_audit tool itself)."""
    out: dict = {}
    bn = str(botte_nn.resolve()).replace("\\", "/").lower()
    for p in scan_root.rglob("*.py"):
        sp = str(p.resolve()).replace("\\", "/").lower()
        name = p.name.lower()
        if name.startswith("test_") or "/nn_audit/" in sp:
            continue
        if sp.startswith(bn) and (
                "/training/" in sp or "/models/" in sp
                or name in ("cli.py", "features.py")):
            continue
        out[sp] = _read(p)
    return out


def audit_models(botte_nn_dir: str | Path, scan_root: str | Path | None = None) -> dict:
    """Audit every model under <botte_nn_dir>/models against its trainer, tests,
    and whether anything in production actually consumes it (wired vs orphan)."""
    base = Path(botte_nn_dir)
    models_dir = base / "models"
    training_dir = base / "training"
    if not models_dir.exists():
        return {"error": f"no models dir at {models_dir}", "models": [], "summary": {}}

    scripts = {p.name: _read(p) for p in training_dir.glob("*.py")} if training_dir.exists() else {}
    test_blob = "\n".join(_read(p) for p in base.glob("test_*.py"))
    root = Path(scan_root) if scan_root else base.parent  # default: skills/
    prod = _production_files(root, base)

    results: list = []
    for mj in sorted(models_dir.glob("*.json")):
        stem = mj.stem
        try:
            meta = json.loads(_read(mj))
        except json.JSONDecodeError:
            meta = {}
        provenance = sorted(k for k in meta if k in PROVENANCE_KEYS)

        real = synth = False
        trainers: list = []
        for name, body in scripts.items():
            if stem not in name and stem not in body:
                continue
            trainers.append(name)
            low = body.lower()
            if any(m in low for m in REAL_MARKERS):
                real = True
            if any(m in body for m in SYNTH_MARKERS):
                synth = True
        data_source = "real" if real else ("synthetic" if synth else "unknown")

        has_provenance = bool(provenance)
        # A "guard" = the model name appears in a test with an equality check.
        has_test_guard = (stem in test_blob and ("==" in test_blob))
        # "wired" = some production file (not infra/tests) references the model.
        usage_files = sorted(Path(sp).name for sp, body in prod.items() if stem in body)
        wired = bool(usage_files)

        if data_source == "real":
            verdict = "grounded" if has_provenance else "grounded (add provenance)"
        elif data_source == "synthetic":
            verdict = ("synthetic — drives behaviour: ground it" if wired
                       else "synthetic + orphan: delete or wire")
        else:
            verdict = "unknown"

        results.append({
            "model": stem, "data_source": data_source, "wired": wired,
            "usage": usage_files,
            "has_provenance": has_provenance, "provenance_keys": provenance,
            "has_test_guard": has_test_guard, "trainers": trainers,
            "verdict": verdict,
            # highest risk = a synthetic net that actually drives behaviour
            "risk": data_source == "synthetic" and wired,
        })

    total = len(results)
    grounded = sum(1 for r in results if r["data_source"] == "real")
    synthetic = sum(1 for r in results if r["data_source"] == "synthetic")
    orphan = sum(1 for r in results if not r["wired"])
    at_risk = sum(1 for r in results if r["risk"])
    score = round(100 * grounded / total) if total else 0
    return {
        "botte_nn": str(base),
        "models": results,
        "summary": {"total": total, "grounded": grounded, "synthetic": synthetic,
                    "unknown": total - grounded - synthetic, "orphan": orphan,
                    "at_risk": at_risk, "grounded_pct": score},
        "cloud_tokens": 0,
    }
