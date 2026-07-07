"""Multi-model local consensus — vote across multiple local models before escalating.

When MULTI_MODEL=True in HarnessSpec, runs the same prompt against N different
local models and takes the majority answer. Only escalates if no consensus.

Supported models: qwen2.5-coder:7b, llama3.2:3b, phi3:mini, gemma2:2b.
Configure models in 'models' field of HarnessSpec.
"""

MULTI_MODEL_DEFAULT = ["qwen2.5-coder:7b", "llama3.2:3b", "phi3:mini"]
MULTI_MODEL_MIN_CONSENSUS = 2  # agree >= this many models
