# Botte Secrète Roadmap

_Last updated: 2026-08-22_

Botte Secrète is a local-first control plane. This roadmap extends its current “cheapest capable verified path” principle with **memory-aware model and expert scheduling**, inspired by dynamic sparse/MoE serving systems such as FreeToken while keeping Botte provider-neutral.

## P0 — Memory-aware local execution

### Goal

Route not only by capability and cost, but also by **where the required capability should live**: GPU VRAM, system RAM, or cold storage.

### Planned primitives

- [ ] Add a provider-neutral `ResidencyTier` abstraction: `hot_vram`, `warm_ram`, `cold_storage`.
- [ ] Extend local backend discovery with per-device memory budget, free VRAM, model footprint, load latency, and measured throughput.
- [ ] Add a residency registry for models, adapters, expert groups, draft models, embeddings, STT/TTS models, and other accelerators.
- [ ] Track last use, hit rate, promotion latency, eviction cost, reliability, and task affinity.
- [ ] Add hard admission control to reject/pause a promotion before OOM rather than recovering after failure.
- [ ] Preserve a static-placement mode as the safe rollback path.

## P0 — Dynamic routing policy

- [ ] Extend `botte route` to score execution paths using capability, verification confidence, latency, token cost, memory pressure, and transfer cost.
- [ ] Introduce `retry -> alternate backend -> abstain/escalate` as the default failure ladder instead of blind retries.
- [ ] Prevent repeated backend/model failures from causing retry storms.
- [ ] Keep routing decisions inspectable in dashboard/event logs with a concise reason for every promotion, eviction, fallback, and escalation.
- [ ] Add policy caps for maximum VRAM occupancy and maximum concurrent model promotions.

## P1 — Predictive prewarming

- [ ] Predict the next likely model/tool/expert from workflow state and prewarm only when expected latency savings exceed promotion cost.
- [ ] Start with deterministic heuristics and recorded traces.
- [ ] Compare against a tiny calibrated classifier only after label provenance and rollback gates exist.
- [ ] Track false prefetches, VRAM churn, wasted transfers, and cold-start latency.

## P1 — Speculative and asymmetric multi-GPU execution

Reference target: commodity Ubuntu hosts with 2 × 12 GB GPUs.

- [ ] Support an asymmetric topology: one GPU for primary inference, the other for draft/speculative work, embeddings, STT/TTS, or hot specialists.
- [ ] Benchmark this against tensor/model split and replicated-model strategies.
- [ ] Treat GPU memories as separate budgets; never report 24 GB as transparent unified VRAM.
- [ ] Measure PCIe traffic and reject placements whose transfer overhead cancels the compute gain.
- [ ] Add graceful degraded mode if one GPU disappears or a CUDA worker fails.

## P1 — MoE / conditional specialist support

- [ ] Add a generic concept of independently schedulable specialists/expert groups without binding Botte to one model family.
- [ ] Allow routing policies to keep frequently used experts hot and promote rare experts on demand.
- [ ] Support expert-cache telemetry: hit rate, miss penalty, promotion bytes, eviction count, and queue time.
- [ ] Add hooks for llama.cpp/LocalAI/Ollama capabilities where supported, but keep the policy layer independent of backend-specific APIs.

## P1 — Local speech residency

- [ ] Treat offline STT and TTS models as first-class schedulable resources.
- [ ] Permit STT/TTS to occupy the secondary GPU only while active and fall back to CPU when interactive latency remains acceptable.
- [ ] Benchmark Whisper/whisper.cpp and locally supported TTS backends with cold/warm/hot start timings.

## P2 — Cross-project scheduler contract

Design a small reusable contract that StoryCore, ShardJEPA experiments, and game/agent runtimes can consume without importing Botte internals.

Proposed minimum contract:

```text
TaskRequirements
  capabilities[]
  latency_class
  reliability_class
  memory_budget
  preferred_device
  fallback_policy

ResourceCandidate
  backend
  model_or_expert
  device
  residency_tier
  load_cost
  expected_latency
  verification_path
```

The scheduler returns a chosen path plus an auditable explanation and fallback sequence.

## Acceptance benchmarks

Every optimization must be compared with the current static/local baseline and report:

- TTFT and median/p95 completion latency;
- tokens/s or task throughput where meaningful;
- peak VRAM per GPU and peak RAM;
- model/expert promotion time and bytes transferred;
- cache hit rate and eviction count;
- success/verification rate;
- retry/fallback/abstention count;
- stability during long-running and concurrent workloads.

A change does **not** graduate merely because it fits a larger model. It must improve useful latency, reliability, cost, or capability on real workflows.
