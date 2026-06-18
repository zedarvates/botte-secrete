"""Project profiler — analyze a project to determine which skills are relevant."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Optional


@dataclass
class ProjectProfile:
    """Profile of a project."""
    path: str = ""
    name: str = ""
    type: str = "unknown"
    languages: dict[str, int] = field(default_factory=dict)  # ext -> file_count
    frameworks: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    has_git: bool = False
    has_github_remote: bool = False
    has_docker: bool = False
    has_ci: bool = False
    package_manager: str = ""
    total_files: int = 0
    total_lines: int = 0


def profile_project(project_path: str) -> ProjectProfile:
    """Profile a project directory to determine its characteristics."""
    profile = ProjectProfile()
    root = Path(project_path).resolve()
    profile.path = str(root)
    profile.name = root.name
    profile.has_git = (root / ".git").exists()

    if not root.is_dir():
        return profile

    # Scan files
    ext_counts: dict[str, int] = {}
    dirs_seen: set[str] = set()

    for fpath in root.rglob("*"):
        # Skip common non-project dirs
        parts = fpath.relative_to(root).parts
        if any(p.startswith(".") and p != ".github" for p in parts):
            continue
        if any(skip in parts for skip in ["node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".next"]):
            continue

        if fpath.is_file():
            profile.total_files += 1
            ext = fpath.suffix
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

            # Track directories
            if len(parts) > 1:
                dirs_seen.add(parts[0])

    profile.languages = dict(sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:10])
    profile.directories = sorted(dirs_seen)

    # Detect frameworks from config files
    framework_detectors = {
        "package.json": _detect_js_framework,
        "pyproject.toml": _detect_python_framework,
        "Cargo.toml": lambda p: ["rust"] if p.exists() else [],
        "go.mod": lambda p: ["go"] if p.exists() else [],
        "requirements.txt": lambda p: ["python"] if p.exists() else [],
        "Dockerfile": lambda p: ["docker"] if p.exists() else [],
        "docker-compose.yml": lambda p: ["docker"] if p.exists() else [],
        "docker-compose.yaml": lambda p: ["docker"] if p.exists() else [],
    }

    for filename, detector in framework_detectors.items():
        f = root / filename
        if f.exists():
            detected = detector(f)
            if detected:
                profile.frameworks.extend(detected)
            if filename in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"):
                profile.has_docker = True

    # Detect CI
    profile.has_ci = (
        (root / ".github" / "workflows").exists() or
        (root / ".gitlab-ci.yml").exists() or
        (root / "Jenkinsfile").exists() or
        (root / ".circleci").exists()
    )

    # Detect package manager
    if (root / "pnpm-lock.yaml").exists():
        profile.package_manager = "pnpm"
    elif (root / "yarn.lock").exists():
        profile.package_manager = "yarn"
    elif (root / "package-lock.json").exists():
        profile.package_manager = "npm"
    elif (root / "poetry.lock").exists():
        profile.package_manager = "poetry"
    elif (root / "Pipfile.lock").exists():
        profile.package_manager = "pipenv"
    elif (root / "requirements.txt").exists():
        profile.package_manager = "pip"

    # Detect GitHub remote
    git_config = root / ".git" / "config"
    if git_config.exists():
        try:
            content = git_config.read_text(encoding="utf-8", errors="replace")
            profile.has_github_remote = "github.com" in content
        except Exception:
            pass

    # Determine project type
    profile.type = _detect_project_type(profile)

    return profile


def _detect_js_framework(package_json: Path) -> list[str]:
    frameworks = []
    try:
        import json
        data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        fw_map = {
            "react": "react", "next": "nextjs", "vue": "vue", "@angular/core": "angular",
            "svelte": "svelte", "express": "express", "fastify": "fastify",
            "nuxt": "nuxt", "remix": "remix", "gatsby": "gatsby",
        }
        for dep, name in fw_map.items():
            if dep in deps:
                frameworks.append(name)

        if "typescript" in deps:
            frameworks.append("typescript")
    except Exception:
        pass
    return frameworks


def _detect_python_framework(pyproject: Path) -> list[str]:
    frameworks = []
    try:
        content = pyproject.read_text(encoding="utf-8", errors="replace")
        fw_patterns = {
            r"django": "django", r"flask": "flask", r"fastapi": "fastapi",
            r"pydantic": "pydantic", r"sqlalchemy": "sqlalchemy",
            r"celery": "celery", r"pytest": "pytest",
        }
        for pattern, name in fw_patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                frameworks.append(name)
    except Exception:
        pass
    return frameworks


def _detect_project_type(profile: ProjectProfile) -> str:
    """Detect the type of project based on its characteristics."""
    exts = set(profile.languages.keys())
    dirs = set(d.lower() for d in profile.directories)
    frameworks = set(f.lower() for f in profile.frameworks)

    # ML/Data
    if exts & {".ipynb", ".h5", ".pkl", ".onnx"} or "ml" in dirs or "models" in dirs:
        return "ml"
    if any(f in frameworks for f in ["pytorch", "tensorflow", "sklearn", "jax"]):
        return "ml"

    # Web frontend
    if exts & {".jsx", ".tsx", ".vue", ".svelte", ".html", ".css", ".scss"}:
        if any(f in frameworks for f in ["react", "vue", "angular", "svelte", "nextjs", "nuxt"]):
            return "web-frontend"

    # Web backend
    if any(f in frameworks for f in ["django", "flask", "fastapi", "express", "fastify"]):
        return "web-backend"

    # CLI tool
    if "cli" in dirs or (exts & {".py"}) and not exts & {".jsx", ".tsx", ".vue"}:
        if "setup.py" in str(profile.path) or "pyproject.toml" in str(profile.path):
            return "cli"

    # Infrastructure
    if exts & {".tf", ".hcl", ".nomad"} or "terraform" in dirs or "ansible" in dirs:
        return "infra"

    # Data
    if exts & {".sql", ".csv", ".parquet", ".avro"} or "data" in dirs or "etl" in dirs:
        return "data"

    # Generic
    if exts & {".py"}:
        return "python"
    if exts & {".ts", ".js"}:
        return "typescript"
    if exts & {".rs"}:
        return "rust"
    if exts & {".go"}:
        return "go"

    return "unknown"