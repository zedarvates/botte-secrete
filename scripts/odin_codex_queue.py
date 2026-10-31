#!/usr/bin/env python3
"""Foreground launcher; does not install a service or alter the native Codex UI."""
from pathlib import Path
import sys

# The foreground script also uses the repository's shared host admission gate.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odin_queue.server import main

if __name__ == "__main__":
    raise SystemExit(main())
