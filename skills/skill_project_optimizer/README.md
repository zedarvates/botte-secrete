# Skill Project Optimizer — Token-Efficient Skill Loading

> *"Don't load 229 skills when you need 12."*

## Problem

```
229 skills total
├── 174 archived (472K tokens waste)
├── 31 active
│   ├── 18 without tags (58%) → can't filter
│   ├── 13 without triggers → blind loading
│   └── Average 2,500 tokens each
└── Total active: ~76K tokens
```

Loading ALL active skills for every project wastes 50-80% of skill tokens.

## Solution

A 3-step workflow:

1. **Scan** — Index all available skills (tags, size, triggers)
2. **Profile** — Analyze project (languages, frameworks, structure)
3. **Optimize** — Match skills to project, generate `.skills-profile`

## Usage

```bash
# 1. Scan all skills
python -m skills.skill_project_optimizer.cli scan

# 2. Profile a project
python -m skills.skill_project_optimizer.cli profile ~/projects/my-app

# 3. Generate optimized skill list
python -m skills.skill_project_optimizer.cli optimize ~/projects/my-app

# 4. Compare savings
python -m skills.skill_project_optimizer.cli compare ~/projects/my-app

# 5. Find skills without tags
python -m skills.skill_project_optimizer.cli tags --missing
```

## The .skills-profile File

Generated in project root — controls which skills are loaded:

```yaml
project:
  name: "my-app"
  type: "web-backend"
  languages: [".py", ".ts"]
  frameworks: ["fastapi", "react"]

skills:
  always:
    - writing-plans
    - code-rules
    - simplify-code

  conditional:
    - github-workflow
    - local-llm-manager

  disabled:
    - ascii-video
    - comfyui

stats:
  total_available: 76570
  total_loaded: 15000
  savings_percent: 80%
```

## Token Savings by Project Type

| Project Type | Tokens Loaded | Savings |
|--------------|--------------|---------|
| Web backend  | ~12,000 | 84% |
| ML pipeline | ~18,000 | 76% |
| CLI tool    | ~8,000  | 89% |
| Full stack  | ~20,000 | 74% |

## Matching Rules

Skills are matched to projects based on:

1. **Always loaded** — Core skills (writing-plans, code-rules)
2. **Language match** — Python skills for Python projects
3. **Framework match** — FastAPI skills for FastAPI projects
4. **Directory match** — `ml/` dir triggers ML skills
5. **Git/GitHub** — GitHub workflow skills when remote detected
6. **Docker/CI** — DevOps skills when Dockerfile/.github present

## Adding Custom Rules

Edit `optimizer.py` and add to `SKILL_MATCHING_RULES`:

```python
(lambda p: "my-tag" in p.frameworks, {"skill-tag"}, "high"),
```
