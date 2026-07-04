# Infra profiles — AMD / Intel GPU

## AMD (ROCm)

For AMD GPUs (RX 6000/7000 series, Radeon Pro):
- Use `ollama` with ROCm backend: `ollama serve` auto-detects
- Recommended models: `llama3.2:3b`, `qwen2.5:7b`, `phi3:mini`
- VRAM budget: 8 GB → 3B params at Q4, 16 GB → 7B at Q4, 32 GB → 13B at Q4

## Intel (Arc / oneAPI)

For Intel Arc GPUs:
- Use `llama.cpp` with SYCL backend: `-ngl 99` offloads all layers
- Recommended models: GGUF Q4_K_M for best speed/quality tradeoff
- VRAM budget: similar to AMD

## Apple Silicon

Already covered in infra_advisor. M1/M2/M3 with 16+ GB unified memory → 7B-13B at Q4.

## Quantized model recommendations by RAM

| RAM | Model | Quant | Speed (tok/s) |
|-----|-------|-------|---------------|
| 8 GB | phi-3-mini (3.8B) | Q4_K_M | ~25 |
| 16 GB | qwen2.5-coder:7b | Q4_K_M | ~35 |
| 16 GB | llama3.2:3b | Q8_0 | ~40 |
| 32 GB | qwen2.5:14b | Q4_K_M | ~20 |
| 64 GB | qwen2.5:32b | Q4_K_M | ~12 |
