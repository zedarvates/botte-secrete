# Local worker benchmark

This benchmark compares Granite 4.2 with an existing local worker on the same
sanitized missions. It runs in `SIMULATE`: it cannot train, activate, route real
work, or promote Granite to `BUILDER`.

## Preconditions

- Serve every candidate from one already-running, private OpenAI-compatible
  endpoint (Ollama, LM Studio, llama.cpp, LocalAI, or vLLM).
- Load the official IBM Granite 4.2 8B `Q4_K_M` GGUF under an unambiguous runtime
  tag, for example `granite42-8b-q4km`. The benchmark never downloads it.
- Keep the comparison worker loaded on the same host and use the same context,
  sampling parameters, repetitions, and sanitized missions.
- Run on the inference host if RAM and per-GPU VRAM measurements are required.
  `nvidia-smi` is sampled read-only; no reboot, driver, BIOS, or GPU setting is
  changed.

Copy and edit the examples outside the repository:

```bash
cp docs/examples/local-worker-benchmark-plan.json /tmp/worker-plan.json
cp docs/examples/local-worker-benchmark-missions.jsonl /tmp/worker-missions.jsonl
python -m skills.local_harness.worker_benchmark \
  --plan /tmp/worker-plan.json \
  --missions /tmp/worker-missions.jsonl \
  --output /tmp/worker-report.json
```

The example corpus is only a wiring fixture. A decision-quality run needs
independently reviewed missions for `SCOUT`, `REQUIREMENTS`, and `VALIDATOR`.
Inputs follow the [plan](schemas/local-worker-benchmark-plan.schema.json) and
[mission](schemas/local-worker-benchmark-mission.schema.json) contracts; output
follows the [report](schemas/local-worker-benchmark.schema.json) contract.
The report records TTFT, throughput, host RAM peak, per-GPU VRAM peak,
structured-output validity, tool-call correctness, mission success, escalation,
and validator disagreement. Missing telemetry is explicit and makes the report
`insufficient_evidence`.

Prompts, raw responses, API keys, local paths, and endpoint URLs are never copied
into the report. Only model identifiers, declared provenance, aggregate metrics,
input hashes, and safe error codes are retained. Two GPUs remain separate
measurements and are never described as pooled VRAM.

## Promotion gate

A `measured_comparable` report is evidence for human review, not permission to
activate a worker. Granite remains limited to `SCOUT`, `REQUIREMENTS`, and
`VALIDATOR`. A later, explicit decision may consider `BUILDER` only if reviewed
task-quality evidence justifies it.
