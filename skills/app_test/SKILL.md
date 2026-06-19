---
name: app_test
description: Local-first GUI/app testing by image matching (SikuliX) — turn a small JSON spec referencing your button images into a runnable SikuliX script and run it locally, using a vision NPU (Hailo-8/10) or local vision model instead of cloud vision. Use when the user wants to test a desktop/game/web app "for real" by clicking buttons, has button images already, or mentions SikuliX, image-matching tests, or local UI tests.
---

# app_test — test apps locally by clicking their buttons

When you build a UI you already have the button images, so an image-matching bot
can drive it — no cloud vision tokens needed. A tiny JSON spec → a runnable
SikuliX script.

## Spec → script → run

```bash
python -m skills.app_test.cli gen tests/login_flow.json     # print the SikuliX script
python -m skills.app_test.cli run tests/login_flow.json --out build
```

```json
{
  "name": "login_flow",
  "image_dir": "tests/images",
  "similarity": 0.8,
  "steps": [
    {"do": "wait",           "image": "login_btn.png", "timeout": 10},
    {"do": "click",          "image": "login_btn.png"},
    {"do": "type",           "text": "user@example.com"},
    {"do": "click",          "image": "submit.png"},
    {"do": "assert_visible", "image": "welcome.png", "timeout": 8},
    {"do": "assert_absent",  "image": "error.png"}
  ]
}
```

Actions: `wait · click · double_click · right_click · type · sleep ·
assert_visible · assert_absent`.

## Running it

Uses **OculiX** (the maintained SikuliX fork: OpenCV matching + embedded
Tesseract OCR, Java) — or any SikuliX. The generated `-r <bundle>` scripts are
drop-in compatible with both.

Install OculiX (Java 11+ required): download the platform "ide" jar from
https://github.com/oculix-org/Oculix/releases and place it at
`~/.oculix/oculixide.jar` (auto-detected), or set `OCULIX_JAR=/path/to/jar`.
`runsikulix`/`oculix` on PATH also work. `run` always generates the `.sikuli`
bundle; it executes it via `java -jar <jar> -r <bundle> -c` when a runner is
found, else it reports how to install one.

Verified: a generated bundle runs end-to-end on OculiX 3.0.4
(`oculixide-3.0.4-windows.jar`) — Jython executes the steps and returns the exit
code (0 = pass).

## Why local / economical

Image matching is CPU-cheap and needs no model. For richer checks (is this screen
*semantically* right?), point verification at a **Hailo-8/10 NPU** or a local
vision model via [[llm_backends]] instead of a paid cloud vision API — 0 cloud
tokens. The generator is deterministic and unit-tested; the GUI run is local.

Related: [[llm_backends]] (local vision backends), [[metrics]].
