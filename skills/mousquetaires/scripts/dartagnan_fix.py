#!/usr/bin/env python3
"""d'Artagnan Fix Script — Apply fixes from Porthos audit, output compact JSON."""

import sys, json, re, subprocess
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from skills.cache import ProjectCache
from skills.diff_language import DiffReport, DiffLine, Op, Sev


def auto_fix_dead_code(filepath: str, line: int, description: str) -> dict | None:
    """Comment out dead code. Returns fix entry or None if unsafe."""
    p = Path(filepath)
    if not p.exists():
        return {"action": "SKIPPED", "file": filepath, "line": line, "error": "file not found"}
    
    lines = p.read_text().split("\n")
    if line < 1 or line > len(lines):
        return {"action": "SKIPPED", "file": filepath, "line": line, "error": "line out of range"}
    
    original = lines[line - 1]
    # SAFETY: don't touch def/class/import/return statements
    if re.match(r'^\s*(def |class |import |from |return |if __name__)', original):
        return {"action": "SKIPPED", "file": filepath, "line": line, "error": "unsafe: def/class/import/return"}
    
    # Comment the dead code
    indent = len(original) - len(original.lstrip())
    lines[line - 1] = " " * indent + "# DEAD CODE: " + original.lstrip()
    p.write_text("\n".join(lines) + "\n")
    
    # Verify it still parses
    result = subprocess.run([sys.executable, "-m", "py_compile", str(p)],
                          capture_output=True, text=True)
    if result.returncode != 0:
        # Rollback
        lines[line - 1] = original
        p.write_text("\n".join(lines) + "\n")
        return {"action": "SKIPPED", "file": filepath, "line": line, "error": "parse error after fix"}
    
    return {"action": "FIXED", "file": filepath, "line": line, "fix": f"CMT::{description[:60]}"}


def main():
    if len(sys.argv) < 4:
        print("Usage: dartagnan_fix.py <project_path> <audit_json> <output_dir>")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    audit_json = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load audit
    audit = json.loads(audit_json.read_text()) if audit_json.exists() else {}
    findings = audit.get("fn", audit.get("findings", []))
    
    print(f"⚔️ d'Artagnan — Fixing {len(findings)} findings...")

    # Cache
    cache = ProjectCache(str(project_path))

    # Apply fixes
    log = []
    files_changed = set()
    
    for f in findings:
        file_ref = f.get("f", f.get("file", ""))
        typ = f.get("t", f.get("type", ""))
        
        # Parse file:line from compact format "file.py:42" or handle dict
        if ":" in str(file_ref):
            parts = file_ref.rsplit(":", 1)
            filepath = str(project_path / parts[0])
            try:
                line = int(parts[1])
            except ValueError:
                line = 0
        else:
            filepath = str(project_path / file_ref)
            line = f.get("line", f.get("l", 0))
        
        desc = f.get("d", f.get("description", ""))
        
        if typ in ("dead", "dead_code") and line:
            result = auto_fix_dead_code(filepath, line, desc)
        else:
            result = {"action": "SKIPPED", "file": file_ref, "line": line, 
                     "error": f"fixer not available for type={typ}"}
        
        if result["action"] == "FIXED":
            files_changed.add(filepath)
        if result:
            log.append(result)

    fixed = sum(1 for e in log if e["action"] == "FIXED")
    skipped = len(log) - fixed

    # Compact output
    report = {
        "ok": fixed,
        "sk": skipped,
        "fc": len(files_changed),
        "fx": [{"f": e.get("file",""), "s": "ok", "t": "fix", 
                "d": e.get("fix","")[:80]} for e in log if e["action"] == "FIXED"],
        "uf": [{"f": e.get("file",""), "s": "warn", "t": "skip", 
                "d": e.get("error","")[:80]} for e in log if e["action"] == "SKIPPED"],
    }
    out = output_dir / "fix-report.json"
    out.write_text(json.dumps(report, indent=2))

    # Also cache it
    cache.set("fix-result", report)

    print(f"\n⚔️ Fixed: {fixed}  Skipped: {skipped}  Files changed: {len(files_changed)}")
    print(f"✅ Report: {out}")


if __name__ == "__main__":
    main()
