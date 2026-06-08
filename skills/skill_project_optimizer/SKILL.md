# Skill Project Optimizer
Per-project skill filtering to reduce token waste.

**Trigger:** When starting work on a new project or when tokens are too high.

**Usage:**
```bash
python3 -m skills.skill_project_optimizer.cli scan
python3 -m skills.skill_project_optimizer.cli profile <project>
python3 -m skills.skill_project_optimizer.cli optimize <project>
python3 -m skills.skill_project_optimizer.cli compare <project>
```

**Module:** `skills/skill_project_optimizer`
**Output:** `.skills-profile` (always/conditional/disabled skills)
**Savings:** 73-83% token reduction
