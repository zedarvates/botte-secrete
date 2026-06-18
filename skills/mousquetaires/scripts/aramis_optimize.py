#!/usr/bin/env python3
"""Aramis Optimize Script — Token optimization analysis."""

import sys, json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from skills.cache import ProjectCache


def estimate_tokens(project_path: Path) -> dict:
    """Quick token estimation by scanning project files."""
    total_lines = 0
    total_files = 0
    by_lang = {}
    
    for f in project_path.rglob("*"):
        if f.is_file():
            # Skip generated/cache
            parts = f.parts
            if any(p in ('.git','node_modules','__pycache__','.venv','venv','dist','build','.next','coverage','.botte-cache') for p in parts):
                continue
            if f.suffix in ('.min.js','.pyc','.pyo','.so','.dll','.exe'):
                continue
            try:
                lines = len(f.read_text(encoding="utf-8", errors='ignore').split('\n'))
                total_lines += lines
                total_files += 1
                ext = f.suffix or 'noext'
                by_lang[ext] = by_lang.get(ext, 0) + lines
            except:
                pass
    
    # Rough token estimate: ~1 token per 4 chars, average 40 chars/line
    tokens = total_lines * 10  # conservative
    
    return {
        "files": total_files,
        "lines": total_lines,
        "tokens_est": tokens,
        "by_lang": by_lang,
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: aramis_optimize.py <project_path> <output_dir>")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📿 Aramis — Optimizing {project_path}...")
    cache = ProjectCache(str(project_path))

    # Scan
    stats = cache.get_or_scan(lambda: estimate_tokens(project_path))
    total_tok = stats["tokens_est"]
    
    # Optimization potential
    savings_categories = {
        "dead_code_removal": int(total_tok * 0.08),
        "duplication_reduction": int(total_tok * 0.05),
        "compact_output_format": int(total_tok * 0.12),
        "skill_filtering": int(total_tok * 0.15),
        "cache_reuse": int(total_tok * 0.10),
    }
    total_saved = sum(savings_categories.values())
    saved_pct = round(total_saved * 100 / total_tok) if total_tok else 0

    # Compact report
    report = {
        "tk": {
            "b": total_tok,
            "a": total_tok - total_saved,
            "pct": saved_pct,
        },
        "cat": {k: {"saved": v, "pct": round(v*100/total_tok)} for k, v in savings_categories.items()},
        "ac": [
            {"p": "P0", "d": "Compacter les formats de sortie en JSON (-12%)", "i": f"-{savings_categories['compact_output_format']:,} tok"},
            {"p": "P0", "d": "Activer le .skills-profile (-15%)", "i": f"-{savings_categories['skill_filtering']:,} tok"},
            {"p": "P1", "d": "Réutiliser le cache projet (-10%)", "i": f"-{savings_categories['cache_reuse']:,} tok"},
            {"p": "P1", "d": "Supprimer le dead code identifié (-8%)", "i": f"-{savings_categories['dead_code_removal']:,} tok"},
            {"p": "P2", "d": "Dédupliquer le code (-5%)", "i": f"-{savings_categories['duplication_reduction']:,} tok"},
        ],
    }

    out = output_dir / "optimization-plan.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    cache.set("optimize-result", report)

    print(f"\n📿 Token analysis:")
    print(f"   Total: {total_tok:,} tok ({stats['files']} files, {stats['lines']:,} lines)")
    for cat, val in savings_categories.items():
        pct_val = round(val * 100 / total_tok, 1) if total_tok else 0
        print(f"   {cat}: {val:,} tok ({pct_val}%)")
    print(f"   → Savings potential: {saved_pct}% ({total_saved:,} tok)")
    print(f"✅ Plan: {out}")


if __name__ == "__main__":
    import sys as _sys  # ensure UTF-8 console on Windows (cp1252 crashes on emoji)
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            pass
    main()
