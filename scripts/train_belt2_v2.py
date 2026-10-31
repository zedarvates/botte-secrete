"""Historical synthetic Belt 2.0 experiment, retained as a code reference.

Source-model replacement is disabled. Use active_learning train to export a
separate candidate from compatible observations, then qualify it independently.
"""
import json, sys
from pathlib import Path
import numpy as np

MODELS_DIR = Path(__file__).parent.parent / "skills" / "botte_nn" / "models"
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.botte_nn import features

def softmax(x):
    e = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e / np.sum(e, axis=-1, keepdims=True)

def relu(x):
    return np.maximum(0, x)

def train_model(X, y, n_hidden, epochs=500, lr=0.02):
    n_in = X.shape[1]; n_out = len(set(y))
    Y = np.zeros((len(y), n_out))
    Y[np.arange(len(y)), y] = 0.9; Y[Y == 0] = 0.05 / n_out
    w1 = np.random.randn(n_in, n_hidden) * np.sqrt(2.0 / (n_in + n_hidden))
    b1 = np.zeros(n_hidden)
    w2 = np.random.randn(n_hidden, n_out) * np.sqrt(2.0 / (n_hidden + n_out))
    b2 = np.zeros(n_out)
    for ep in range(epochs):
        z1 = X @ w1 + b1; h = relu(z1); z2 = h @ w2 + b2; p = softmax(z2)
        loss = -np.mean(np.sum(Y * np.log(p + 1e-9), axis=1))
        dz2 = (p - Y) / len(X); dw2 = h.T @ dz2; db2 = np.sum(dz2, axis=0)
        dh = dz2 @ w2.T; dz1 = dh * (z1 > 0)
        dw1 = X.T @ dz1; db1 = np.sum(dz1, axis=0)
        clr = lr * (1 - ep / epochs * 0.5)
        w2 -= clr * dw2; b2 -= clr * db2; w1 -= clr * dw1; b1 -= clr * db1
        if ep == epochs - 1:
            acc = np.mean(np.argmax(p, axis=1) == y)
            conf = np.max(p, axis=1).mean()
            print(f"    loss={loss:.4f} acc={acc:.2%} avg_conf={conf:.2f}")
    return w1, b1, w2, b2

def save_model(name, w1, b1, w2, b2, labels, extra=None):
    raise RuntimeError("legacy source-model replacement disabled; export a separate candidate")

def fvec(model, values):
    """Convert feature dict to ordered list matching the model's schema."""
    return [values[s.name] for s in features.SCHEMAS[model]]

def train_compressibility():
    print("\n📦 compressibility_predictor...")
    X, y = [], []
    for _ in range(100):
        X.append(fvec("compressibility_predictor", features.compressibility_values("hello world"))); y.append(0)
        X.append(fvec("compressibility_predictor", features.compressibility_values("ERROR " * 1000))); y.append(2)
        X.append(fvec("compressibility_predictor", features.compressibility_values('[{"x":1},{"x":2}]' * 50))); y.append(1)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 12)
    save_model("compressibility_predictor", w1,b1,w2,b2, ["none","delta","heavy"], {"num_samples":len(X)})

def train_context_pruning():
    print("\n✂️  context_pruning_predictor...")
    X, y = [], []
    for _ in range(100):
        X.append(fvec("context_pruning_predictor", features.context_pruning_values(500, 2, "doc", 0.9, 0.8))); y.append(0)
        X.append(fvec("context_pruning_predictor", features.context_pruning_values(50000, 15, "mixed", 0.1, 0.1))); y.append(1)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 12)
    save_model("context_pruning_predictor", w1,b1,w2,b2, ["keep","prune"], {"num_samples":len(X)})

def train_skip_agent():
    print("\n⏭️  skip_agent_predictor...")
    X, y = [], []
    for _ in range(200):
        X.append(fvec("skip_agent_predictor", features.skip_agent_values(0.0, 0.0, "audit", 0.0, 0.9))); y.append(0)
    for _ in range(200):
        X.append(fvec("skip_agent_predictor", features.skip_agent_values(0.9, 0.9, "audit", 0.8, 0.1))); y.append(1)
    # Also add edge cases
    for _ in range(100):
        X.append(fvec("skip_agent_predictor", features.skip_agent_values(0.5, 0.5, "audit", 0.5, 0.5))); y.append(0)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 14, epochs=800)
    save_model("skip_agent_predictor", w1,b1,w2,b2, ["execute","skip"], {"num_samples":len(X)})

def train_cloud_escalation():
    print("\n☁️  cloud_escalation_predictor...")
    X, y = [], []
    for _ in range(200):
        X.append(fvec("cloud_escalation_predictor", features.cloud_escalation_values(0.1, "audit", 0.0, 0.1, 0.9))); y.append(0)
        X.append(fvec("cloud_escalation_predictor", features.cloud_escalation_values(0.4, "analyze", 0.1, 0.4, 0.5))); y.append(1)
        X.append(fvec("cloud_escalation_predictor", features.cloud_escalation_values(0.9, "research", 0.4, 0.9, 0.1))); y.append(2)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 14, epochs=800)
    save_model("cloud_escalation_predictor", w1,b1,w2,b2, ["local_small","local_big","cloud"], {"num_samples":len(X)})

def train_response_length():
    print("\n📏 response_length_predictor...")
    X, y = [], []
    for _ in range(100):
        X.append(fvec("response_length_predictor", features.response_length_values("simple", "audit", 0.1, "short"))); y.append(0)
        X.append(fvec("response_length_predictor", features.response_length_values("explain", "report", 0.5, "medium"))); y.append(1)
        X.append(fvec("response_length_predictor", features.response_length_values("design", "analyze", 0.9, "long"))); y.append(2)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 12)
    save_model("response_length_predictor", w1,b1,w2,b2, ["short","medium","long"], {"num_samples":len(X)})

def train_tool_call():
    print("\n🔧 tool_call_predictor...")
    X, y = [], []
    for _ in range(100):
        X.append(fvec("tool_call_predictor", features.tool_call_values(False, False, "ask", 0.3, 0.8))); y.append(0)
        X.append(fvec("tool_call_predictor", features.tool_call_values(True, True, "deploy", 0.8, 0.3))); y.append(1)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 14)
    save_model("tool_call_predictor", w1,b1,w2,b2, ["llm_only","use_tool"], {"num_samples":len(X)})

def train_semantic_cache():
    print("\n💾 semantic_cache_hit_predictor...")
    X, y = [], []
    for _ in range(100):
        X.append(fvec("semantic_cache_hit_predictor", features.semantic_cache_values(
            "unknown synthetic query", cache_density=0.1, cache_hit_history=0.1,
        ))); y.append(0)
        X.append(fvec("semantic_cache_hit_predictor", features.semantic_cache_values(
            "matching synthetic query", cache_density=0.9, cache_hit_history=0.9,
            eligible_cache_density=0.8, eligible_vocabulary_coverage=1.0,
            length_neighbor_ratio=1.0,
        ))); y.append(1)
    X = np.array(X); y = np.array(y)
    w1,b1,w2,b2 = train_model(X, y, 14)
    save_model("semantic_cache_hit_predictor", w1,b1,w2,b2, ["miss","hit"], {"num_samples":len(X)})

def verify():
    print("\n🔍 Verification...")
    from skills.auto_router.nn_belt2 import (
        skip_agent_hint, cloud_escalation_hint, response_length_hint,
        tool_call_hint, semantic_cache_hint,
    )
    tests = [
        ("skip_agent", skip_agent_hint(0.0, "audit", 0.0, 0.9), "execute"),
        ("skip_agent", skip_agent_hint(0.9, "audit", 0.8, 0.1), "skip"),
        ("cloud_esc", cloud_escalation_hint(0.1, "audit", 0.0, 0.1), "local_small"),
        ("cloud_esc", cloud_escalation_hint(0.9, "research", 0.4, 0.9), "cloud"),
        ("resp_len", response_length_hint("simple", "audit", 0.1, "short"), "short"),
        ("resp_len", response_length_hint("design", "analyze", 0.9, "long"), "long"),
        ("tool", tool_call_hint(False, False, "ask", 0.3), "llm_only"),
        ("tool", tool_call_hint(True, True, "fix", 0.8), "use_tool"),
        ("cache", semantic_cache_hint("unknown synthetic query", cache_density=0.1,
                                     cache_hit_history=0.1), "miss"),
        ("cache", semantic_cache_hint("matching synthetic query", cache_density=0.9,
                                     cache_hit_history=0.9, eligible_cache_density=0.8,
                                     eligible_vocabulary_coverage=1.0,
                                     length_neighbor_ratio=1.0), "hit"),
    ]
    ok = True
    for name, result, expected in tests:
        if result and result[1] > 0.6:
            label, conf = result
            status = "✅" if label == expected else "⚠️"
            print(f"  {status} {name:<15} → {label:<12} ({conf:.2f}) expected={expected}")
        else:
            print(f"  ❌ {name:<15} → abstain expected={expected}")
            ok = False
    return ok

def main():
    print("Legacy trainer disabled before training or writes; use "
          "python -m skills.botte_nn.active_learning train for a separate candidate.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
