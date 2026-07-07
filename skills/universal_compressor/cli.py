"""
CLI for Universal Compressor — compress files or stdin.

Usage:
    python -m skills.universal_compressor.cli compress file.log --type log
    echo '{"a":1}' | python -m skills.universal_compressor.cli compress --type json
    python -m skills.universal_compressor.cli stats
"""

from __future__ import annotations

import sys
from pathlib import Path
from skills.universal_compressor.compressor import compress, stats, flush_store


def cmd_compress(args: list[str]):
    """Compress a file or stdin."""
    content_type = "auto"
    reversible = False
    file_path = None

    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            content_type = args[i + 1]
            i += 2
        elif args[i] == "--reversible":
            reversible = True
            i += 1
        elif not args[i].startswith("-"):
            file_path = args[i]
            i += 1
        else:
            i += 1

    if file_path:
        content = Path(file_path).read_text(encoding="utf-8")
    else:
        content = sys.stdin.read()

    result = compress(content, content_type=content_type, reversible=reversible)

    print(f"Type: {result.content_type}")
    print(f"Strategy: {result.strategy}")
    print(f"Size: {result.original_size} → {result.compressed_size} bytes ({result.ratio:.0%})")
    if result.reversible_key:
        print(f"Key: {result.reversible_key}")
    print()
    print(result.data)


def cmd_stats(_args: list[str]):
    """Show compressor stats."""
    s = stats()
    print(f"Stored originals: {s['stored_originals']}")
    print(f"Total original bytes: {s['total_original_bytes']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m skills.universal_compressor.cli <compress|stats> [args]")
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "compress":
        cmd_compress(args)
    elif cmd == "stats":
        cmd_stats(args)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
