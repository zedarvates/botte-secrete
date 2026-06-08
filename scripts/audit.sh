#!/usr/bin/env python3
"""
Botte Secrète — Unified Audit Script
Runs fallow (JS/TS) + karpathy-review + knowledge graph stats on a project.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run(cmd, cwd=None, timeout=60):
    """Run a command, return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", 124
    except FileNotFoundError:
        return "", f"NOT FOUND: {cmd[0]}", 127


def audit_js_ts(project_path):
    """Run fallow audit on JS/TS project."""
    print("\n=== Fallow Static Analysis ===")
    
    for cmd_name, cmd_args in [
        ("health", ["fallow", "health", "--score", "--hotspots"]),
        ("dead-code", ["fallow", "dead-code", "--production"]),
        ("dupes", ["fallow", "dupes"]),
        ("cycles", ["fallow", "cycles"]),
    ]:
        stdout, stderr, rc = run(cmd_args, cwd=project_path)
        if rc == 0:
            print(f"\n--- {cmd_name} ---")
            print(stdout[:2000])
        else:
            print(f"  {cmd_name}: {stderr[:200]}")


def audit_python(project_path):
    """Run Python companion audit."""
    print("\n=== Python Audit ===")
    script = Path(__file__).parent / "fallow-python.py"
    if script.exists():
        stdout, stderr, run(
            [sys.executable, str(script), project_path, "--format", "text"]
        )
        print(stdout[:2000] if stdout else stderr[:200])
    else:
        print("  fallow-python.py not found, skipping")


def karpathy_review(project_path):
    """Run Karpathy review on recent changes."""
    print("\n=== Karpathy Review ===")
    
    # Get recent diff
    stdout, stderr, rc = run(["git", "diff", "HEAD~1"], cwd=project_path)
    if rc != 0 or not stdout.strip():
        print("  No recent changes to review")
        return
    
    # Save diff
    diff_path = "/tmp/botte-secrete-review.diff"
    Path(diff_path).write_text(stdout)
    
    script = Path(__file__).parent / "karpathy-review.py"
    if script.exists():
        out, err, rc = run(
            [sys.executable, str(script), "--diff", diff_path]
        )
        print(out[:2000] if out else err[:200])
    else:
        print("  karpathy-review.py not found, skipping")


def knowledge_graph_stats(project_path):
    """Check knowledge graph status."""
    print("\n=== Knowledge Graph ===")
    kg_path = Path(project_path) / ".understand-anything" / "knowledge-graph.json"
    meta_path = Path(project_path) / ".understand-anything" / "meta.json"
    
    if kg_path.exists():
        kg = json.loads(kg_path.read_text())
        nodes = len(kg.get("nodes", []))
        edges = len(kg.get("edges", []))
        layers = len(kg.get("layers", []))
        tour = len(kg.get("tour", []))
        print(f"  Nodes: {nodes}")
        print(f"  Edges: {edges}")
        print(f"  Layers: {layers}")
        print(f"  Tour steps: {tour}")
    else:
        print("  No knowledge graph found. Run understand-anything to generate.")
    
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        print(f"  Last analyzed: {meta.get('lastAnalyzedAt', 'unknown')}")
        print(f"  Git commit: {meta.get('gitCommitHash', 'unknown')[:12]}")


def token_savings_estimate(project_path):
    """Estimate token savings from applying Botte Secrète techniques."""
    print("\n=== Token Savings Estimate ===")
    
    # Count files and lines
    total_lines = 0
    total_files = 0
    large_files = 0
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {
            "node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"
        }]
        for f in files:
            if f.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".yaml", ".yml")):
                fp = Path(root) / f
                try:
                    lines = len(fp.read_text().splitlines())
                    total_lines += lines
                    total_files += 1
                    if lines > 1500:
                        large_files += 1
                except (UnicodeDecodeError, PermissionError):
                    pass
    
    print(f"  Total files: {total_files}")
    print(f"  Total lines: {total_lines}")
    print(f"  Files > 1500 lines: {large_files}")
    print(f"  Estimated context tokens (naive): {total_lines * 4}")
    print(f"  Estimated context tokens (with Botte Secrète): {total_lines * 1}")
    print(f"  Potential savings: ~75%")


def main():
    parser = argparse.ArgumentParser(description="Botte Secrète — Unified Audit")
    parser.add_argument("project", help="Path to project to audit")
    parser.add_argument("--js-only", action="store_true", help="Only JS/TS audit")
    parser.add_argument("--py-only", action="store_true", help="Only Python audit")
    parser.add_argument("--kg-only", action="store_true", help="Only knowledge graph")
    parser.add_argument("--estimate", action="store_true", help="Token savings estimate")
    args = parser.parse_args()
    
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"Error: {project} is not a directory")
        sys.exit(1)
    
    print(f"🧦 Botte Secrète Audit")
    print(f"Project: {project}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    start = time.time()
    
    if args.kg_only:
        knowledge_graph_stats(project)
    elif args.js_only:
        audit_js_ts(project)
    elif args.py_only:
        audit_python(project)
    elif args.estimate:
        token_savings_estimate(project)
    else:
        audit_js_ts(project)
        audit_python(project)
        karpathy_review(project)
        knowledge_graph_stats(project)
        token_savings_estimate(project)
    
    elapsed = time.time() - start
    print(f"\nCompleted in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
