#!/usr/bin/env python3
"""d'Artagnan Fix Script — Apply fixes from audit report."""

import sys
import json
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print("Usage: dartagnan_fix.py <project_path> <audit_report.json>")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    audit_report = json.loads(Path(sys.argv[2]).read_text())

    findings = (
        audit_report.get("findings", {}).get("error", []) +
        audit_report.get("findings", {}).get("warning", [])
    )

    print(f"⚔️ d'Artagnan — Fixing {len(findings)} findings in {project_path}")

    fixed = 0
    remaining = []

    for finding in findings:
        file_path = finding.get("file", "")
        description = finding.get("description", "")
        finding_type = finding.get("type", "")

        if not file_path:
            continue

        full_path = project_path / file_path
        if not full_path.exists():
            remaining.append(f"{file_path} — file not found")
            continue

        try:
            if finding_type == "dead_code":
                # Comment out dead code line
                content = full_path.read_text()
                lines = content.splitlines()
                line_num = finding.get("line", 0)
                if 0 < line_num <= len(lines):
                    original = lines[line_num - 1]
                    # Don't double-comment
                    if "# DEAD CODE" not in original:
                        lines[line_num - 1] = f"# DEAD CODE (Porthos): {original}"
                        full_path.write_text("\n".join(lines))
                        fixed += 1
                        print(f"  ✅ {file_path}:{line_num} — dead code commented")
                    else:
                        fixed += 1  # Already fixed
                else:
                    remaining.append(f"{file_path}:{line_num} — line out of range")

            elif finding_type == "secret":
                remaining.append(f"{file_path} — MANUAL FIX REQUIRED (security)")

            elif finding_type == "feature_flag":
                remaining.append(f"{file_path} — feature flag cleanup (manual)")

            elif finding_type == "duplication":
                remaining.append(f"{file_path} — deduplication (manual)")

            elif finding_type == "boundary":
                remaining.append(f"{file_path} — architecture fix (manual)")

            elif finding_type == "complexity":
                remaining.append(f"{file_path} — refactoring (manual)")

            else:
                remaining.append(f"{file_path} — {description} (not auto-fixable)")

        except Exception as e:
            remaining.append(f"{file_path} — error: {e}")

    print(f"\n📊 Fixed: {fixed}/{len(findings)}")
    print(f"⚠️  Remaining: {len(remaining)}")

    if remaining:
        print("\nRemaining (manual fix required):")
        for r in remaining[:30]:
            print(f"  • {r}")

    # Save fix report
    fix_report = {
        "project": str(project_path),
        "fixed": fixed,
        "total": len(findings),
        "remaining": remaining,
    }
    fix_path = project_path / "fix-report.json"
    with open(fix_path, "w") as f:
        json.dump(fix_report, f, indent=2, default=str)
    print(f"\n✅ Fix report: {fix_path}")


if __name__ == "__main__":
    main()
