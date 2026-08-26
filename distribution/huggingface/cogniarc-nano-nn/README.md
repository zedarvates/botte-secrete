---
license: mit
language:
- en
library_name: generic
pipeline_tag: text-classification
tags:
- arc-agi-3
- micro-nn
- rust
- numpy
- tiny-ml
- domain-classification
- action-prediction
- embedded
- token-free
---

# CogniARC Nano-NN — experimental ARC classifiers

Small feed-forward networks trained with NumPy and inferable with Rust for
experiments in the public
[CogniARC](https://github.com/zedarvates/cogniarc) research harness.

They are **comparison baselines**, not general ARC solvers. The current CogniARC
pipeline is rule-first and may use a micro-NN only as a hint or comparison.
Low-confidence output must abstain or escalate to a separately verified path.

## Bundled models

| Model | Role | Authority |
|---|---|---|
| `domain_classifier.json` | Compare movement/rotation/transform/hybrid hypotheses | Advisory |
| `action_predictor.json` | Estimate whether a candidate action may succeed | Advisory |
| `captcha_classifier.json` | Experimental CAPTCHA-family classification fixture | Research only; never a bypass mechanism |

The historical accuracy values in older cards were measured on small or
synthetic splits. They are not claims of ARC-AGI-3 generalization. Consult the
source repository's dev/holdout reports and reproduce the relevant benchmark
before drawing conclusions.

## Where it is used

- [CogniARC source](https://github.com/zedarvates/cogniarc)
- [`micro_predictors.py`](https://github.com/zedarvates/cogniarc/blob/main/cogniarc/micro_predictors.py)
- [Rules-vs-NN benchmark](https://github.com/zedarvates/cogniarc/blob/main/scripts/benchmark_rules_vs_nn.py)

## Minimal JSON inference

```python
import json
import numpy as np

with open("domain_classifier.json", encoding="utf-8") as stream:
    model = json.load(stream)

x = np.asarray([1.0, 1.0, 0.3, 0.35, 0.45, 0.02], dtype=float)
for index, (weights, bias, activation) in enumerate(zip(
    model["weights"], model["biases"], model["activations"]
)):
    matrix = np.asarray(weights).reshape(model["layers"][index + 1], model["layers"][index])
    x = x @ matrix.T + np.asarray(bias)
    if activation == "relu":
        x = np.maximum(0, x)
    elif activation == "sigmoid":
        x = 1 / (1 + np.exp(-x))
    elif activation == "softmax":
        shifted = x - np.max(x)
        x = np.exp(shifted) / np.exp(shifted).sum()

print(x)
```

Use the source feature extractors rather than inventing anonymous feature
vectors. The example demonstrates the stored feed-forward format only.

## Licence

Released under the [MIT License](https://github.com/zedarvates/cogniarc/blob/main/LICENSE).
