# Botte Secrète — Architecture

## Module Dependency Graph

```
                    ┌─────────────────────┐
                    │   botte-secrete     │
                    │   (main README)     │
                    └─────────┬───────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │  Code   │          │  Agent  │          │ Hardware│
   │ Quality │          │  Workflows         │  Accel  │
   └────┬────┘          └────┬────┘          └────┬────┘
        │                     │                     │
   ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
   │code-rules│         │dynamic- │          │hailo-   │
   │karpathy │          │workflows│          │vision   │
   │fallow   │          │simplify │          │comfyui  │
   │         │          │second-  │          │bonsai   │
   │         │          │brain    │          │         │
   └─────────┘          └─────────┘          └─────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼───────────┐
                    │   Shared Scripts    │
                    │   (scripts/)        │
                    └─────────────────────┘
```

## Data Flow

### Token Reduction Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                      INPUT: Raw Task                         │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  P1: Think Before Code  │  karpathy-guidelines
              │  (plan → verify)        │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  P2: Simple Solution    │  code-rules
              │  (stdlib-first)         │
              └────────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ Fallow  │      │Simplify │      │Knowledge│
    │ Audit   │      │ Review  │      │ Graph   │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
              ┌────────────▼────────────┐
              │  RTK Terminal Compact  │  rtk
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Second Brain (Qdrant)  │  hermes-second-brain
              │  (no repeated context)  │
              └────────────┬────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              OUTPUT: Token-Efficient Response                │
│              (~70-80% reduction vs naive)                    │
└──────────────────────────────────────────────────────────────┘
```

### Hardware Acceleration Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                    Vision Tasks                               │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Hailo-8 (EUREKAI)     │
              │  - YOLOv8 detection     │
              │  - ResNet-18 classify   │
              │  - PaddleOCR v5         │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Structured JSON Output  │
              │  (objects, text, labels)│
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Qdrant Index           │
              │  (vector search)        │
              └────────────┬────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              Token-Efficient Context                         │
│              (50 tokens vs 4000 for full image)              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    Generation Tasks                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ComfyUI  │      │Bonsai   │      │Local    │
    │(SD/FLUX)│      │Image 4B │      │LLM      │
    │:8188    │      │:8788    │      │(llama.  │
    │         │      │WebGPU   │      │cpp)     │
    └─────────┘      └─────────┘      └─────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              Zero Cloud API Costs                             │
└──────────────────────────────────────────────────────────────┘
```

## File Conventions

- `README.md` — English, project root
- `RULES.md` — Module-specific rules
- `PIPELINE.md` — Hardware/data flow docs
- `scripts/` — Executable scripts (Python preferred)
- `configs/` — Configuration files
- `workflows/` — Reusable workflow definitions
