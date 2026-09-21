"""Caveman CLI — inspect input size and print optional concise-output prompts."""

import argparse
import json
from pathlib import Path

from skills.console_utf8 import force_utf8
from skills.caveman.prompts import PROMPTS, get_prompt, list_levels


def count_tokens(text: str) -> int:
    """Rough token estimate (4 chars ≈ 1 token)."""
    return (len(text) + 3) // 4


def compress_text(text: str, level: str = "full") -> dict:
    """Analyze unchanged text; a style prompt alone proves no output savings.

    The historical field names remain for callers. Both token counts are
    explicitly heuristic estimates of the same complete input.
    """
    original_tokens = count_tokens(text)
    
    return {
        "original_chars": len(text),
        "original_bytes": len(text.encode("utf-8")),
        "original_tokens": original_tokens,
        "level": level,
        "estimated_tokens": original_tokens,
        "token_count_method": "estimated_chars_div_4",
        "saved_tokens": 0,
        "savings_pct": 0.0,
        "style_savings_pct": None,
        "applied": False,
        "compressed": text,
    }


def compress_file(path: str, level: str = "full", dry_run: bool = False) -> dict:
    """Read a file for size analysis. Neither mode writes or truncates it."""
    p = Path(path)
    if not p.is_file():
        return {"error": f"File not found: {path}"}
    
    try:
        with p.open(encoding="utf-8", newline="") as stream:
            original = stream.read()
    except (OSError, UnicodeError) as exc:
        return {"error": f"Cannot read UTF-8 file: {exc}"}
    
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
    """Report file size without inventing a generated response."""
    result = compress_file(args.target, args.level, args.dry_run)
    
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            print(f"❌ {result['error']}")
            return 1
        print(f"📄 {result['file']}")
        print(f"   Lines: {result['lines']} | Code blocks: {result['code_blocks']} | URLs: {result['urls']}")
        print(f"   Size: {result['original_bytes']} UTF-8 bytes; ~{result['original_tokens']} tokens (character estimate)")
        print("   Analysis only: input unchanged; style savings not measured.")
    return 1 if "error" in result else 0


def cmd_prompt(args: argparse.Namespace) -> int:
    """Print the system prompt for a caveman level."""
    prompt = get_prompt(args.level)
    print(prompt)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show prompt sizes, with no unmeasured savings claim."""
    print("📊 Caveman Prompt Sizes (character-based estimates)\n")
    print(f"{'Level':<12} {'Prompt tokens':<14}")
    print("-" * 35)
    for level, prompt in PROMPTS.items():
        tokens = count_tokens(prompt)
        print(f"{level:<12} ~{tokens:<13}")
    print("Style savings require paired model outputs and a quality check.")
    print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List available levels."""
    for level in list_levels():
        print(level)
    return 0


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(description="Caveman — size analysis and optional concise-output prompts")
    sub = p.add_subparsers(dest="cmd", required=True)
    
    # compress
    s = sub.add_parser("compress", help="Analyze file size (read-only; no model call)")
    s.add_argument("target", help="UTF-8 file to analyze")
    s.add_argument("--level", choices=list_levels(), default="full", help="Style label; no model call")
    s.add_argument("--dry-run", action="store_true", help="Compatibility flag; file analysis is always read-only")
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
    raise SystemExit(main())
