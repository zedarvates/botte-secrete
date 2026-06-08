#!/usr/bin/env python3
"""Aramis Optimize Script — Optimize project tokens and performance."""

import sys
import json
from pathlib import Path

# Setup path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from skills.skill_project_optimizer.scanner import scan_skills
from skills.skill_project_optimizer.profiler import profile_project
from skills.skill_project_optimizer.optimizer import optimize_skills, generate_skills_profile


def main():
    if len(sys.argv) < 3:
        print("Usage: aramis_optimize.py <project_path> <output_dir>")
        sys.exit(1)

    project_path = sys.argv[1]
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📿 Aramis — Optimizing {project_path}...")

    # Scan skills
    print("  Scanning available skills...")
    scan = scan_skills("~/.hermes/skills")
    print(f"    {len(scan.skills)} skills found, {scan.active_tokens:,} active tokens")

    # Profile project
    print("  Profiling project...")
    profile = profile_project(project_path)
    print(f"    Type: {profile.type}")
    print(f"    Languages: {', '.join(list(profile.languages.keys())[:5])}")

    # Optimize
    print("  Running optimization...")
    result = optimize_skills(scan, profile)

    # Save
    plan = {
        "project": result.profile.name,
        "type": result.profile.type,
        "languages": result.profile.languages,
        "frameworks": result.profile.frameworks,
        "matched_skills": [(s.name, p) for s, p in result.matched_skills],
        "excluded_skills": [(s.name, r) for s, r in result.excluded_skills],
        "stats": {
            "total_available": result.total_available_tokens,
            "total_loaded": result.total_loaded_tokens,
            "savings": result.savings_tokens,
            "savings_percent": result.savings_percent,
        },
    }

    output_base = output_dir / "optimization-plan"
    with open(str(output_base) + ".json", "w") as f:
        json.dump(plan, f, indent=2, default=str)

    # Generate .skills-profile in project
    generate_skills_profile(result, Path(project_path) / ".skills-profile")

    print(f"\n📊 Tokens: {result.total_available_tokens:,} → {result.total_loaded_tokens:,} ({result.savings_percent:.0f}% saved)")
    print(f"📊 Skills: {len(result.matched_skills)} loaded, {len(result.excluded_skills)} excluded")
    print(f"✅ Report saved to {output_base}.json")
    print(f"✅ .skills-profile written to {project_path}/.skills-profile")


if __name__ == "__main__":
    main()
