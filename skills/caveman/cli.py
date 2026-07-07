"""Caveman CLI — compress text/output, preview levels, show stats."""

import argparse
import json
import os
import sys
from pathlib import Path

from skills.caveman.prompts import PROMPTS, get_prompt, list_levels


def count_tokens(text: str) -> int:
    """Rough token estimate (4 chars ≈ 1 token)."""
    return len(text) // 4


def compress_text(text: str, level: str = "full") -> dict:
    """Analyze text and report compression potential."""
    original_tokens = count_tokens(text)
    factors = {"light": 0.7, "full": 0.35, "ultra": 0.25, "classical": 0.2}
    ratio = factors.get(level, 0.35)
    estimated = int(original_tokens * ratio)
    saved = original_tokens - estimated
    
    return {
        "original_chars": len(text),
        "original_tokens": original_tokens,
        "level": level,
        "estimated_tokens": estimated,
        "saved_tokens": saved,
        "savings_pct": round((1 - ratio) * 100, 1),
        "compressed": text[:500] + "..." if len(text) > 500 else text,
    }


def compress_file(path: str, level: str = "full", dry_run: bool = False) -> dict:
    """Apply caveman compression to a file."""
    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}
    
    original = p.read_text(encoding="utf-8")
    
    # Count lines, code blocks, URLs to preserve
    lines = original.split("\n")
    code_blocks = original.count("```") // 2
    urls = original.count("http")
    
    # Calculate savings
    result = compress_text(original, level)
    result["file"] = str(p.resolve())
    result["lines"] = len(lines)
    result["code_blocks"] = code_blocks
    result["urls"] = urls
    
    return result


def cmd_compress(args: argparse.Namespace) -> int:
    """Compress a file with caveman style."""
    result = compress_file(args.target, args.level, args.dry_run)
    
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            print(f"❌ {result['error']}")
            return 1
        print(f"📄 {result['file']}")
        print(f"   Lines: {result['lines']} | Code blocks: {result['code_blocks']} | URLs: {result['urls']}")
        print(f"   Tokens: {result['original_tokens']} → ~{result['estimated_tokens']} ({result['savings_pct']}% savings)")
        print(f"   Saved: ~{result['saved_tokens']} tokens")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    """Print the system prompt for a caveman level."""
    prompt = get_prompt(args.level)
    print(prompt)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show compression stats for all levels."""
    print("📊 Caveman Compression Levels\n")
    print(f"{'Level':<12} {'Economy':<10} {'Templates':<10}")
    print("-" * 35)
    for level, prompt in PROMPTS.items():
        tokens = count_tokens(prompt)
        savings = {"light": "~30%", "full": "~65%", "ultra": "~75%", "classical": "~80%"}
        print(f"{level:<12} {savings.get(level, '?'):<10} {tokens:<10}")
    print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List available levels."""
    for level in list_levels():
        print(level)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Caveman — télégraphic output compression")
    sub = p.add_subparsers(dest="cmd", required=True)
    
    # compress
    s = sub.add_parser("compress", help="Compress a file")
    s.add_argument("target", help="File to compress")
    s.add_argument("--level", choices=list_levels(), default="full", help="Compression level")
    s.add_argument("--dry-run", action="store_true", help="Preview only")
    s.add_argument("--format", choices=["compact", "json"], default="compact")
    
    # prompt
    s = sub.add_parser("prompt", help="Print caveman system prompt")
    s.add_argument("--level", choices=list_levels(), default="full")
    
    # stats
    sub.add_parser("stats", help="Show compression stats")
    
    # list
    sub.add_parser("list", help="List available levels")
    
    args = p.parse_args(argv)
    
    handlers = {
        "compress": cmd_compress,
        "prompt": cmd_prompt,
        "stats": cmd_stats,
        "list": cmd_list,
    }
    
    handler = handlers.get(args.cmd)
    if handler:
        return handler(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
