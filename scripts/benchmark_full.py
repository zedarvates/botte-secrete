"""Benchmark complet Botte Secrète — mesure les économies des 14 modules.

Simule un projet réel (cogniarc, kanboard, ou un dossier quelconque)
et mesure les économies de chaque module d'optimisation.

Usage:
    python scripts/benchmark_full.py
    python scripts/benchmark_full.py --dir ../cogniarc
    python scripts/benchmark_full.py --json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skills.console_utf8 import force_utf8  # noqa: E402 — avant tout print d'émoji

force_utf8()


# Sample content that mimics real agent workloads
SAMPLE_CODE = """# main.py
import os
import sys
from typing import Optional

def process_data(items: list[str], max_size: Optional[int] = None) -> dict:
    \"\"\"Process items with optional size limit.\"\"\"
    result = {}
    for item in items[:max_size]:
        try:
            processed = item.strip().lower()
            if processed:
                key = hash(processed) % 1000
                result[key] = processed
        except Exception as e:
            print(f"Error processing {item}: {e}")
    return result

def validate_input(data: dict) -> bool:
    \"\"\"Validate input dictionary.\"\"\"
    required = {"name", "type", "version"}
    return required.issubset(data.keys())

if __name__ == "__main__":
    items = ["Test-1", "Test-2", "Test-3", "ITEM_4", "item_5"]
    print(process_data(items))
"""

SAMPLE_LOG = """2026-07-06 10:00:01 INFO  Starting server on port 8080
2026-07-06 10:00:02 INFO  Database connection established
2026-07-06 10:00:03 WARN  Memory usage: 85%
2026-07-06 10:00:04 INFO  Request GET /api/users took 245ms
2026-07-06 10:00:05 ERROR ConnectionError: Connection refused to database replica
2026-07-06 10:00:06 INFO  Retry attempt 1/3...
2026-07-06 10:00:07 INFO  Retry attempt 2/3...
2026-07-06 10:00:08 INFO  Retry attempt 3/3...
2026-07-06 10:00:09 CRITICAL All retries exhausted, failing over
""" * 10  # Repeat to simulate real log volume

SAMPLE_JSON = json.dumps({
    "users": [{"id": i, "name": f"user_{i}", "email": f"user{i}@test.com",
               "roles": ["admin", "editor", "viewer"]} for i in range(50)],
    "metadata": {"total": 50, "page": 1, "page_size": 50,
                 "filters": {"active": True, "role": "admin"}},
})

SAMPLE_PROMPT = """You are an AI assistant helping with code review.
Please analyze the following code for potential issues:

```python
def unsafe_function(user_input):
    import os
    os.system(f"echo {user_input}")
```

Identify security vulnerabilities and suggest fixes.
Consider: injection attacks, input validation, error handling.
"""


def format_bytes(n: int) -> str:
    if n < 1000: return f"{n}B"
    if n < 1_000_000: return f"{n/1000:.1f}KB"
    return f"{n/1_000_000:.1f}MB"


class Benchmark:
    """Mesure les économies de tous les modules d'optimisation."""

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()
        self.results: dict[str, dict] = {}
        self.start_time = time.time()

    def _sample_task_files(self) -> list[tuple[str, str]]:
        """Collect representative files from project."""
        samples = [("code.py", SAMPLE_CODE), ("server.log", SAMPLE_LOG),
                   ("response.json", SAMPLE_JSON), ("prompt.txt", SAMPLE_PROMPT)]
        return samples

    def benchmark_compressors(self):
        """Test universal_compressor on all content types."""
        print("\n📦 Universal Compressor...")
        from skills.universal_compressor.compressor import compress

        for name, content in self._sample_task_files():
            result = compress(content, content_type="auto")
            savings = round((1 - result.ratio) * 100, 1)
            self.results[f"compress_{name}"] = {
                "module": "universal_compressor",
                "input": result.original_size,
                "output": result.compressed_size,
                "savings_pct": savings,
                "strategy": result.strategy,
            }
            print(f"  {name:<20} {result.original_size:>8} → {result.compressed_size:<8} ({savings}%) [{result.strategy}]")

    def benchmark_token_shaper(self):
        """Test token shaping on various query types."""
        print("\n🎛️  Token Shaper...")
        from skills.token_shaper.shaper import TokenShaper

        queries = [
            ("list files", "audit", 0.1),
            ("fix security vulnerability", "fix", 0.9),
            ("explain architecture", "analyze", 0.5),
            ("urgent deploy fix", "fix", 1.0),
        ]

        shaper = TokenShaper()
        for query, agent, criticality in queries:
            config = shaper.shape(query, agent)
            self.results[f"shape_{query[:15]}"] = {
                "module": "token_shaper",
                "level": config.level.value,
                "compress_ratio": config.compress_ratio,
                "output_target": config.output_tokens_target,
            }
            print(f"  {query:<30} {agent:<10} → {config.level.value:<12} (ratio: {config.compress_ratio})")

    def benchmark_prefix_pruner(self):
        """Test prefix pruning on mixed content."""
        print("\n✂️  Prefix Pruner...")
        from skills.prefix_pruner.pruner import prune_content, PrefixTree

        # Build mixed context with system prompt + skills + memory sections
        mixed = f"""# System
You are an AI coding assistant with access to project files and tools.

# Skills
Available: code analysis, security scanning, testing, deployment.

# Memory
Previous tasks: fixed auth bug, refactored API, added tests.
Last session: reviewed PR #42, found 3 vulnerabilities.

# Context
{json.dumps(SAMPLE_JSON, indent=2)[:500]}

# Code to review
{SAMPLE_CODE}
"""
        tree = PrefixTree()
        result = prune_content(mixed, tree, strategy="auto")

        orig_tok = len(mixed) // 4
        comp_tok = len(result) // 4
        savings = round((1 - comp_tok / orig_tok) * 100, 1)

        self.results["prefix_prune"] = {
            "module": "prefix_pruner",
            "input": orig_tok,
            "output": comp_tok,
            "savings_pct": savings,
        }
        print(f"  Context: {orig_tok} → {comp_tok} tokens ({savings}%)")

    def benchmark_context_slicer(self):
        """Test context slicing."""
        print("\n🧩 Context Slicer...")
        from skills.context_slicer.cli import detect_slices, select_slices

        content = f"""# Code Review
{SAMPLE_CODE}

# Debug Logs
{SAMPLE_LOG[:500]}

# API Response
{json.dumps(SAMPLE_JSON, indent=2)[:300]}

# Configuration
port: 8080
debug: true
max_connections: 100
"""
        slices = detect_slices(content)
        budget = 100  # tokens
        selected = select_slices(slices, "find security issues", max_tokens=budget)

        total_tok = sum(s.token_count for s in slices)
        selected_tok = sum(s.token_count for s in selected)

        self.results["context_slice"] = {
            "module": "context_slicer",
            "total_slices": len(slices),
            "selected_slices": len(selected),
            "input": total_tok,
            "output": selected_tok,
            "savings_pct": round((1 - selected_tok / max(total_tok, 1)) * 100, 1),
        }
        print(f"  {len(slices)} slices → {len(selected)} selected ({selected_tok}/{total_tok} tok)")

    def benchmark_belt2(self):
        """Test all 7 Belt 2.0 predictors."""
        print("\n🧠 Micro-NN Belt 2.0...")
        from skills.auto_router.nn_belt2 import (
            compressibility_hint, skip_agent_hint,
            cloud_escalation_hint, response_length_hint,
            tool_call_hint, semantic_cache_hint,
        )

        tests = [
            ("compressibility", compressibility_hint(SAMPLE_LOG), "logs"),
            ("skip_agent", skip_agent_hint(agent_type="audit"), "audit"),
            ("cloud_escalation", cloud_escalation_hint(task_type="audit"), "audit"),
            ("response_length", response_length_hint(query_type="simple"), "simple query"),
            ("tool_call", tool_call_hint(has_code=True), "code task"),
            ("semantic_cache", semantic_cache_hint(), "new query"),
        ]

        for name, result, context in tests:
            if result:
                label, conf = result
                self.results[f"belt_{name}"] = {
                    "module": f"belt2_{name}",
                    "prediction": label,
                    "confidence": round(conf, 2),
                }
                print(f"  {name:<20} → {label:<12} (conf: {conf:.2f}) [{context}]")
            else:
                self.results[f"belt_{name}"] = {
                    "module": f"belt2_{name}",
                    "prediction": None,
                    "confidence": 0,
                }
                print(f"  {name:<20} → abstain [{context}]")

    def run(self) -> dict:
        """Run all benchmarks."""
        print(f"\n🧦 BOTTE SECRÈTE — Full Pipeline Benchmark")
        print(f"{'='*60}")
        print(f"Project: {self.project_dir}")
        print()

        self.benchmark_compressors()
        self.benchmark_token_shaper()
        self.benchmark_prefix_pruner()
        self.benchmark_context_slicer()
        self.benchmark_belt2()

        # Calculate totals
        compress_savings = sum(
            r.get("input", 0) - r.get("output", 0)
            for r in self.results.values()
            if r.get("module") == "universal_compressor"
        )
        total_input = sum(
            r.get("input", 0)
            for r in self.results.values()
            if r.get("input", 0) > 0
        )
        total_output = sum(
            r.get("output", 0)
            for r in self.results.values()
            if r.get("output", 0) > 0
        )

        elapsed = time.time() - self.start_time

        summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "elapsed_seconds": round(elapsed, 1),
            "total_modules_tested": len(self.results),
            "modules": self.results,
            "total_input_chars": total_input,
            "total_output_chars": total_output,
            "total_compression_ratio": round(total_output / max(total_input, 1), 3),
            "estimated_monthly_savings_kb": (total_input - total_output) * 1000 // 1024,
        }

        # Print summary
        print(f"\n{'='*60}")
        print(f"📊 BENCHMARK SUMMARY")
        print(f"{'='*60}")
        print(f"Modules tested: {len(self.results)}")
        print(f"Total input:    {format_bytes(total_input)}")
        print(f"Total output:   {format_bytes(total_output)}")
        print(f"Compression:    {round((1-total_output/max(total_input,1))*100,1)}%")
        print(f"Elapsed:        {elapsed:.1f}s")

        return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Botte Secrète Full Benchmark")
    parser.add_argument("--dir", default=".", help="Project directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    bench = Benchmark(args.dir)
    results = bench.run()

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
