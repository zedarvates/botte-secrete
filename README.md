# 🧦 Botte Secrète — Token Efficiency Toolkit

> *"La meilleure optimisation est la soustraction."* — Karpathy

A unified toolkit for reducing AI token consumption, improving code quality,
and running intelligent agents efficiently on local hardware.

## Why "Botte Secrète"?

In French, "botte secrète" means "secret weapon" — the hidden technique that
gives you an edge. This repo is exactly that: a collection of proven patterns,
rules, and tools that dramatically reduce token usage while improving output
quality.

## What's Inside

| Module | Purpose | Token Impact |
|--------|---------|-------------|
| `code-rules` | Coding standards: stdlib-first, flat architecture, data-oriented | -30% context |
| `karpathy-guidelines` | 4 principles to reduce LLM errors in coding | -40% rework |
| `fallow` | Static analysis: dead code, duplication, cycles | -20% codebase bloat |
| `simplify-code` | Parallel 3-agent code review & cleanup | -25% post-edit tokens |
| `understand-anything` | Codebase knowledge graph for navigation | -50% exploration tokens |
| `dynamic-workflows` | 6 workflow patterns (classify, fan-out, adversarial, etc.) | -35% agent turns |
| `hermes-second-brain` | Karpathy-pattern second brain with Qdrant | -60% repeated context |
| `rtk` | Terminal command rewriting & compaction | -40% terminal output tokens |
| `hailo-vision` | Edge AI vision (OCR, classification, detection) | -100% cloud vision API |
| `comfyui` | Local image generation | -100% cloud generation API |

## Hardware Acceleration

### Hailo-8 (EUREKAI 192.168.1.47)
- **YOLOv8m** — object detection at 30+ FPS
- **ResNet-18** — image classification
- **PaddleOCR v5** — text extraction (detection + recognition)
- **SSD MobileNet v1** — lightweight detection
- **NanoDet RepVGG** — nano detection
- Zero cloud API costs, runs on 15W TDP

### ComfyUI (EUREKAI 192.168.1.47:8188)
- Local Stable Diffusion pipeline
- API-driven workflow execution
- Zero cloud generation costs

### Bonsai Image (local WebGPU)
- Ternary 4B image model
- Runs on AMD Radeon 780M via WebGPU
- Offline-ready after first download

## Quick Start

```bash
# Clone
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete

# Install shared dependencies
pip install -r requirements.txt  # (mostly stdlib, minimal deps)

# Run a code audit
./scripts/audit.sh ~/your-project

# Generate a knowledge graph
python3 scripts/knowledge_graph.py ~/your-project

# Run Karpathy review on a diff
python3 skills/karpathy-guidelines/scripts/karpathy-review.py --diff changes.patch

# Check Hailo-8 status
python3 scripts/hailo_status.py
```

## Architecture

```
botte-secrete/
├── docs/                    # Documentation (English)
├── scripts/                 # Shared scripts & entry points
├── skills/                  # Individual skill modules
│   ├── code-rules/          # Coding standards & rules
│   ├── karpathy-guidelines/ # LLM anti-patterns
│   ├── fallow/              # Static analysis (JS/TS)
│   ├── simplify-code/       # Parallel review
│   ├── understand-anything/ # Knowledge graph
│   ├── dynamic-workflows/   # 6 workflow patterns
│   ├── hermes-second-brain/ # Second brain (Qdrant)
│   ├── hailo-vision/        # Hailo-8 vision pipeline
│   ├── comfyui/             # ComfyUI integration
│   └── rtk/                 # Terminal token saver
├── configs/                 # Shared configurations
└── workflows/               # Reusable workflow definitions
```

## Token Savings Breakdown

| Technique | Savings | How |
|-----------|---------|-----|
| stdlib-first coding | 30% | No framework boilerplate in context |
| Karpathy P1 (think first) | 40% | Less rework from misunderstood requirements |
| Fallow dead code removal | 20% | Smaller codebase = less context |
| Knowledge graph navigation | 50% | Targeted file reading vs full scan |
| Second brain (Qdrant) | 60% | No repeated context injection |
| RTK terminal compaction | 40% | Shorter terminal outputs |
| Hailo-8 local vision | 100% | Zero cloud API tokens for OCR/detection |
| ComfyUI local generation | 100% | Zero cloud API tokens for images |
| **Combined potential** | **~70-80%** | **Cumulative effect across pipeline** |

## Roadmap

- [x] Initial structure
- [ ] Consolidate all skills into unified repo
- [ ] RTK terminal compactor v2
- [ ] Hailo-8 vision pipeline scripts
- [ ] ComfyUI workflow templates
- [ ] Knowledge graph auto-update hooks
- [ ] CI/CD integration (pre-commit hooks)
- [ ] Dashboard for token savings metrics
- [ ] Multi-language support (FR/EN/JP)

## License

MIT — Use freely, improve constantly.

## Author

Sylvain Galliez ([@zedarvates](https://github.com/zedarvates))
