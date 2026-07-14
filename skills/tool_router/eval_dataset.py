"""Build a deterministic, bilingual seed corpus for router evaluation.

The generated JSONL is intentionally synthetic and small in vocabulary: it is a
quality gate for wiring and safety, not training data for a general model.
"""

from __future__ import annotations

import json
from pathlib import Path


def build_seed_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    templates = (
        ("Lis le fichier {path}", "read_file", {"path": "README.md"}),
        ("Read local file {path}", "read_file", {"path": "README.md"}),
        ("Lance le contrôle du projet", "run_checkup", {}),
        ("Run the project health check", "run_checkup", {}),
        ("Lis", None, {}),
        ("Read", None, {}),
        ("Fais quelque chose d'inconnu", None, {}),
        ("Do an unknown action", None, {}),
    )
    paths = ("README.md", "AGENTS.md", "pyproject.toml", "docs/plans/roadmap.md", "skills/test_e2e.py")
    for index in range(240):
        query, tool_name, arguments = templates[index % len(templates)]
        path = paths[index % len(paths)]
        resolved_arguments = {key: (path if value == "README.md" else value) for key, value in arguments.items()}
        cases.append({
            "id": f"seed-{index + 1:03d}",
            "language": "fr" if index % len(templates) in (0, 2, 4, 6) else "en",
            "query": query.format(path=path),
            "expected_tool": tool_name,
            "expected_arguments": resolved_arguments,
            "kind": "valid" if tool_name else ("ambiguous" if index % len(templates) in (4, 5) else "abstain"),
        })
    return cases


def write_seed_dataset(path: str | Path) -> int:
    destination = Path(path)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for case in build_seed_cases():
            handle.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(build_seed_cases())
