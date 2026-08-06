#!/usr/bin/env python3
"""Generate reproducible README visuals from Botte's bundled demo and benchmark."""

from __future__ import annotations

import argparse
import html
import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.benchmark_full import Benchmark
from skills.demo.demo import run_scripted


DEFAULT_OUTPUT = REPO / "docs" / "assets"
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _benchmark_data() -> dict:
    with redirect_stdout(io.StringIO()):
        return Benchmark(REPO).run()


def _benchmark_svg(data: dict) -> str:
    modules = data["modules"]
    values = [
        ("Python sample", modules["compress_code.py"]["savings_pct"]),
        ("Log sample", modules["compress_server.log"]["savings_pct"]),
        ("JSON sample", modules["compress_response.json"]["savings_pct"]),
        ("Prefix pruning", modules["prefix_prune"]["savings_pct"]),
        ("Context slicing", modules["context_slice"]["savings_pct"]),
    ]
    width, height = 1200, 650
    chart_left, chart_top, chart_width = 250, 150, 820
    bar_height, gap = 54, 26
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Inter,Segoe UI,Arial,sans-serif}.label{fill:#d8e3f0;font-size:24px}.value{fill:#08111f;font-size:21px;font-weight:700}.outside{fill:#d8e3f0}.note{fill:#8fa7bf;font-size:18px}.title{fill:#f4f8fb;font-size:38px;font-weight:700}.subtitle{fill:#8fa7bf;font-size:21px}</style>",
        '<rect width="1200" height="650" rx="28" fill="#08111f"/>',
        '<text class="title" x="70" y="70">Measured reduction on bundled samples</text>',
        '<text class="subtitle" x="70" y="108">Higher is better · rerun with python scripts/generate_docs_visuals.py</text>',
    ]
    colors = ["#55d6be", "#4cc9f0", "#7b8cff", "#b48cff", "#ff8fab"]
    for index, ((label, value), color) in enumerate(zip(values, colors)):
        y = chart_top + index * (bar_height + gap)
        value_width = max(8.0, chart_width * value / 100)
        value_class = "value outside" if value < 15 else "value"
        value_x = chart_left + value_width + 14 if value < 15 else chart_left + 15
        parts.extend([
            f'<text class="label" x="70" y="{y + 36}">{html.escape(label)}</text>',
            f'<rect x="{chart_left}" y="{y}" width="{chart_width}" height="{bar_height}" rx="14" fill="#132238"/>',
            f'<rect x="{chart_left}" y="{y}" width="{value_width:.1f}" height="{bar_height}" rx="14" fill="{color}"/>',
            f'<text class="{value_class}" x="{value_x:.1f}" y="{y + 36}">{value:.1f}%</text>',
        ])
    overall = (1 - data["total_compression_ratio"]) * 100
    parts.extend([
        f'<text class="note" x="70" y="590">Bundled synthetic corpus · overall character reduction: {overall:.1f}% · {html.escape(data["timestamp"][:10])}</text>',
        '<text class="note" x="1130" y="590" text-anchor="end">Results vary by content; code is intentionally conservative.</text>',
        "</svg>",
    ])
    return "\n".join(parts)


def _demo_svg() -> str:
    frame = list(run_scripted(delay=0, clear=False))[-1]
    lines = ANSI_RE.sub("", frame).rstrip().splitlines()
    width = max(1120, max(len(line) for line in lines) * 10 + 100)
    height = len(lines) * 28 + 150
    text_lines = []
    for index, line in enumerate(lines):
        text_lines.append(
            f'<text x="52" y="{104 + index * 28}">{html.escape(line)}</text>'
        )
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Cascadia Mono,Consolas,monospace;font-size:20px;white-space:pre;fill:#d8e3f0}.caption{font-family:Inter,Segoe UI,Arial,sans-serif;font-size:18px;fill:#8fa7bf}</style>',
        f'<rect width="{width}" height="{height}" rx="26" fill="#08111f"/>',
        '<circle cx="42" cy="38" r="9" fill="#ff6b6b"/><circle cx="70" cy="38" r="9" fill="#ffd166"/><circle cx="98" cy="38" r="9" fill="#55d6be"/>',
        '<text class="caption" x="132" y="45">botte demo scripted · deterministic · offline</text>',
        *text_lines,
        "</svg>",
    ])


def _monte_cristo_svg() -> str:
    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" viewBox="0 0 1200 620">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#55d6be"/></marker></defs>',
        '<style>text{font-family:Inter,Segoe UI,Arial,sans-serif}.title{fill:#f4f8fb;font-size:38px;font-weight:700}.subtitle{fill:#8fa7bf;font-size:20px}.node-title{fill:#f4f8fb;font-size:22px;font-weight:700}.node-copy{fill:#b7c8d9;font-size:17px}.pill{fill:#08111f;font-size:16px;font-weight:700}.arrow{fill:none;stroke:#55d6be;stroke-width:4;marker-end:url(#arrow)}</style>',
        '<rect width="1200" height="620" rx="28" fill="#08111f"/>',
        '<text class="title" x="60" y="66">Monte Cristo · independent strategic review</text>',
        '<text class="subtitle" x="60" y="102">Questions the shared frame before a costly or irreversible commitment</text>',
        '<rect x="60" y="155" width="245" height="92" rx="18" fill="#132238" stroke="#4cc9f0" stroke-width="2"/>',
        '<text class="node-title" x="84" y="190">Blue team</text><text class="node-copy" x="84" y="220">Improvements and evidence</text>',
        '<rect x="60" y="270" width="245" height="92" rx="18" fill="#132238" stroke="#ff8fab" stroke-width="2"/>',
        '<text class="node-title" x="84" y="305">Red team</text><text class="node-copy" x="84" y="335">Challenges and risks</text>',
        '<rect x="60" y="385" width="245" height="92" rx="18" fill="#132238" stroke="#7b8cff" stroke-width="2"/>',
        '<text class="node-title" x="84" y="420">Primary evidence</text><text class="node-copy" x="84" y="450">Repository, tests, sources</text>',
        '<path class="arrow" d="M305 201 C360 201 360 280 410 280"/><path class="arrow" d="M305 316 L410 316"/><path class="arrow" d="M305 431 C360 431 360 352 410 352"/>',
        '<rect x="410" y="215" width="300" height="205" rx="24" fill="#39204f" stroke="#b48cff" stroke-width="3"/>',
        '<text class="node-title" x="446" y="260">MONTE CRISTO</text>',
        '<text class="node-copy" x="446" y="296">Blind first-principles pass</text><text class="node-copy" x="446" y="326">Observed vs inferred facts</text><text class="node-copy" x="446" y="356">Falsifiable strategic moves</text>',
        '<rect x="446" y="378" width="132" height="28" rx="14" fill="#b48cff"/><text class="pill" x="512" y="398" text-anchor="middle">READ-ONLY</text>',
        '<path class="arrow" d="M710 316 L790 316"/>',
        '<rect x="790" y="175" width="350" height="282" rx="24" fill="#132238" stroke="#55d6be" stroke-width="3"/>',
        '<text class="node-title" x="825" y="217">Bounded verdict</text>',
        '<rect x="825" y="244" width="82" height="32" rx="16" fill="#55d6be"/><text class="pill" x="866" y="266" text-anchor="middle">KEEP</text>',
        '<rect x="920" y="244" width="96" height="32" rx="16" fill="#4cc9f0"/><text class="pill" x="968" y="266" text-anchor="middle">REPAIR</text>',
        '<rect x="1029" y="244" width="88" height="32" rx="16" fill="#7b8cff"/><text class="pill" x="1073" y="266" text-anchor="middle">RETIRE</text>',
        '<rect x="825" y="292" width="112" height="32" rx="16" fill="#ff8fab"/><text class="pill" x="881" y="314" text-anchor="middle">REPLACE</text>',
        '<rect x="950" y="292" width="167" height="32" rx="16" fill="#ffd166"/><text class="pill" x="1033" y="314" text-anchor="middle">INVESTIGATE</text>',
        '<text class="node-copy" x="825" y="360">Evidence · blast radius · next gate</text>',
        '<text class="node-copy" x="825" y="393">Strongest counter-case included</text>',
        '<text class="node-copy" x="825" y="426">Maximum twelve prioritized moves</text>',
        '<path class="arrow" d="M965 457 L965 505"/>',
        '<rect x="715" y="505" width="425" height="72" rx="20" fill="#1d3049" stroke="#ffd166" stroke-width="2"/>',
        '<text class="node-title" x="745" y="537">Human approval gate</text><text class="node-copy" x="745" y="562">A separate authorized agent implements approved moves</text>',
        '</svg>',
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    data = _benchmark_data()
    paths = [
        _write(args.output / "benchmark-compression.svg", _benchmark_svg(data)),
        _write(args.output / "routing-demo.svg", _demo_svg()),
        _write(args.output / "monte-cristo-governance.svg", _monte_cristo_svg()),
    ]
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
