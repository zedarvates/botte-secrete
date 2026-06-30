#!/usr/bin/env python3
"""Distill error_classifier from REAL labelled errors instead of synthetic noise.

The shipped micro-NNs are trained on `np.random` + hand-coded rules, so they encode
invented rules, not reality — error_classifier even maps a ValueError traceback to
"syntax". This is a proof-of-concept of the fix: a small corpus of *real* error
messages, each with its true class, featurised with the deterministic extractor
(`features.error_classifier_values` — the "teacher"), then the micro-NN is retrained
on those real (features -> label) pairs.

    python -m skills.botte_nn.training.distill_error_classifier          # report only
    python -m skills.botte_nn.training.distill_error_classifier --save   # write weights

It prints the synthetic model's accuracy vs the distilled model's on a held-out split.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from skills.botte_nn import features
from skills.botte_nn.cli import _predict_python, _MODELS_DIR
from skills.botte_nn.training.train import TinyNN

# class index -> real-world error message templates (label = the index)
CORPUS: dict[int, list[str]] = {
    0: [  # syntax
        "SyntaxError: invalid syntax",
        '  File "app.py", line 10\n    def f(\n         ^\nSyntaxError: invalid syntax',
        "IndentationError: unexpected indent",
        "SyntaxError: unexpected EOF while parsing",
        "SyntaxError: EOL while scanning string literal",
    ],
    1: [  # runtime
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        "ValueError: invalid literal for int() with base 10: 'x'",
        "KeyError: 'user_id'",
        "IndexError: list index out of range",
        "AttributeError: 'NoneType' object has no attribute 'name'",
        "ZeroDivisionError: division by zero",
    ],
    2: [  # network
        "ConnectionError: HTTPSConnectionPool(host='api'): Max retries exceeded",
        "ConnectionRefusedError: [Errno 111] Connection refused",
        "socket.gaierror: [Errno -2] Name or service not known",
        "ssl.SSLError: certificate verify failed",
        "urllib.error.URLError: <urlopen error unreachable>",
    ],
    3: [  # permission
        "PermissionError: [Errno 13] Permission denied: '/etc/secret'",
        "Access denied",
        "403 Forbidden",
        "OSError: [Errno 1] Operation not permitted",
    ],
    4: [  # timeout
        "TimeoutError: timed out",
        "socket.timeout: timed out",
        "requests.exceptions.ReadTimeout: Read timed out",
        "concurrent.futures.TimeoutError",
        "deadline exceeded",
    ],
    5: [  # resource
        "MemoryError",
        "OSError: [Errno 28] No space left on device",
        "Killed (out of memory)",
        "RuntimeError: CUDA out of memory",
    ],
}
_TB = "Traceback (most recent call last):\n  File \"x.py\", line 42, in <module>\n"
_EXIT = [1, 2, 137]


def build_dataset():
    """Each template x {exit codes} x {bare, traceback-wrapped} -> (features, label)."""
    X, y = [], []
    for cls, templates in CORPUS.items():
        for t in templates:
            for code in _EXIT:
                for wrap in (False, True):
                    text = (_TB + t) if wrap else t
                    vec = features.featurize("error_classifier",
                                             features.error_classifier_values(text, exit_code=code))
                    X.append(vec)
                    y.append(cls)
    return np.array(X, dtype=float), np.array(y, dtype=int)


def _acc_synthetic(model_path, X, y):
    correct = 0
    for xi, yi in zip(X, y):
        out = _predict_python(str(model_path), list(xi))
        if int(np.argmax(out)) == int(yi):
            correct += 1
    return correct / len(y)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for _s in (sys.stdout, sys.stderr):
        rc = getattr(_s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    X, y = build_dataset()
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(y))
    n_test = max(6, len(y) // 5)
    te, tr = idx[:n_test], idx[n_test:]
    Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]

    print(f"== distill error_classifier ==  {len(y)} real samples "
          f"({len(tr)} train / {len(te)} held-out)")

    model_path = _MODELS_DIR / "error_classifier.json"
    syn_acc = _acc_synthetic(model_path, Xte, yte)

    Y = np.zeros((len(ytr), 6))
    Y[np.arange(len(ytr)), ytr] = 1.0
    np.random.seed(0)
    model = TinyNN([12, 16, 6], ["relu", "softmax"])
    model.train(Xtr, Y, epochs=1500, lr=0.05, verbose=False)
    dist_acc = float(np.mean(model.predict(Xte).argmax(axis=1) == yte))

    labels = ["syntax", "runtime", "network", "permission", "timeout", "resource"]
    ve = features.error_classifier_values("ValueError: invalid literal for int()", exit_code=1)
    vvec = features.featurize("error_classifier", ve)
    syn_ve = labels[int(np.argmax(_predict_python(str(model_path), vvec)))]
    dist_ve = labels[int(model.predict(np.array([vvec])).argmax())]

    print(f"  synthetic model  : held-out accuracy {syn_acc:.0%}   | ValueError -> '{syn_ve}'")
    print(f"  distilled model  : held-out accuracy {dist_acc:.0%}   | ValueError -> '{dist_ve}'")
    print(f"  Δ accuracy: {dist_acc - syn_acc:+.0%}")

    if "--save" in argv:
        if dist_acc <= syn_acc:
            print("  (not saving — distilled is not better)")
            return 0
        import json
        model_path.write_text(json.dumps(model.export_json(), indent=2), encoding="utf-8")
        print(f"  ✅ saved distilled weights -> {model_path}"
              f"  (rebuild embedded Rust with embed_weights.py if you use the binary)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
