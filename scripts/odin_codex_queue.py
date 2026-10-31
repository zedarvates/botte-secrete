#!/usr/bin/env python3
"""Foreground launcher; does not install a service or alter the native Codex UI."""
from odin_queue.server import main

if __name__ == "__main__":
    raise SystemExit(main())
