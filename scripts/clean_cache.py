#!/usr/bin/env python3
"""Clean development caches: .botte-cache/, .pytest_cache/, __pycache__/, .mypy_cache/
Usage: python scripts/clean_cache.py [--dry-run]
"""
import shutil, sys, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIRS = [".botte-cache", ".pytest_cache", ".mypy_cache", ".ruff_cache"]

def clean(dry_run=False):
    total = 0
    for dname in DIRS:
        for p in REPO.rglob(dname):
            if p.is_dir():
                size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                total += size
                if not dry_run:
                    shutil.rmtree(p, ignore_errors=True)
                print(f"  {'[DRY]' if dry_run else 'DEL'} {p.relative_to(REPO)} ({size//1024} KB)")
    # __pycache__ everywhere
    for p in REPO.rglob("__pycache__"):
        if p.is_dir():
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            total += size
            if not dry_run:
                shutil.rmtree(p, ignore_errors=True)
    print(f"\nTotal: {total//1024} KB {'(dry run)' if dry_run else 'freed'}")
    return total

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    clean(dry_run=args.dry_run)
