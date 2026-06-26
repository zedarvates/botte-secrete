"""pipeline_dsl — définir des pipelines en YAML.

Permet de créer des pipelines custom sans écrire de code Python.
Les pipelines sont définis en YAML et exécutés par le meta-harness.

Exemple de pipeline YAML :
    name: pre-commit-check
    description: "Run before every commit"
    steps:
      - name: scan
        agent: security_scanner
        args:
          fail_on: critical
        on_fail: block

      - name: explore
        agent: fast_context
        query: "find dangerous patterns"

      - name: fix
        agent: dartagnan
        depends_on: [scan]

Usage :
    python -m skills.meta_harness.pipeline_dsl run pipeline.yaml
    python -m skills.meta_harness.pipeline_dsl validate pipeline.yaml
    python -m skills.meta_harness.pipeline_dsl list
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from skills.meta_harness import MetaHarness
from skills.meta_harness.orchestrator import Step, PipelinePlan


# ── Built-in pipelines (disponibles sans fichier YAML) ──

_BUILTIN_PIPELINES: dict[str, dict] = {
    "pre-commit": {
        "name": "pre-commit",
        "description": "Scan sécurité + tests rapides avant commit",
        "steps": [
            {"agent": "security_scanner", "args": {"fail_on": "critical"},
             "on_fail": "block"},
            {"agent": "fast_context", "query": "find secrets, API keys"},
        ],
    },
    "nightly-audit": {
        "name": "nightly-audit",
        "description": "Audit complet de nuit",
        "steps": [
            {"agent": "fast_context", "query": "full codebase scan"},
            {"agent": "security_scanner", "args": {"fail_on": "info"}},
            {"agent": "porthos"},
            {"agent": "rochefort"},
            {"agent": "test"},
        ],
    },
    "quick-fix": {
        "name": "quick-fix",
        "description": "Audit rapide + correction",
        "steps": [
            {"agent": "porthos"},
            {"agent": "dartagnan"},
            {"agent": "test"},
        ],
    },
}


@dataclass
class PipelineStep:
    """Une étape de pipeline définie en YAML."""
    name: str = ""
    agent: str = ""
    args: dict = field(default_factory=dict)
    query: str = ""
    depends_on: list[str] = field(default_factory=list)
    on_fail: str = "continue"  # continue | block | skip


@dataclass
class PipelineDef:
    """Définition complète d'un pipeline YAML."""
    name: str
    description: str = ""
    steps: list[PipelineStep] = field(default_factory=list)
    version: str = "1.0"


def parse_yaml(text: str) -> Optional[PipelineDef]:
    """Parse un texte YAML en PipelineDef.

    Utilise yaml (PyYAML) si dispo, sinon un parseur minimal.
    """
    try:
        import yaml
        data = yaml.safe_load(text)
    except ImportError:
        data = _parse_minimal_yaml(text)

    if not data or "name" not in data:
        return None

    pipeline = PipelineDef(
        name=data.get("name", "unnamed"),
        description=data.get("description", ""),
    )

    for s in data.get("steps", []):
        step = PipelineStep(
            name=s.get("name", s.get("agent", "step")),
            agent=s.get("agent", ""),
            args=s.get("args", {}),
            query=s.get("query", ""),
            depends_on=s.get("depends_on", []),
            on_fail=s.get("on_fail", "continue"),
        )
        pipeline.steps.append(step)

    return pipeline


def _parse_minimal_yaml(text: str) -> dict:
    """Parseur YAML minimal (stdlib only, sans PyYAML).

    Supporte seulement le sous-ensemble nécessaire :
    - clé: valeur
    - listes avec tirets
    - dictionnaires imbriqués
    """
    result: dict = {}
    current_list: list = []
    in_list = False
    current_dict: dict = {}
    in_dict = False
    dict_key = ""

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            # Élément de liste
            in_list = True
            item = stripped[2:].strip()
            if ":" in item and not item.startswith("'"):
                k, v = item.split(":", 1)
                current_dict[k.strip()] = _parse_value(v.strip())
            else:
                current_list.append(_parse_value(item))
        elif in_list:
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                current_dict[k.strip()] = _parse_value(v.strip())
            else:
                result["steps"] = current_list
                if current_dict:
                    current_list.append(current_dict)
                in_list = False
                current_list = []
                current_dict = {}
                k, v = stripped.split(":", 1)
                result[k.strip()] = _parse_value(v.strip())
        else:
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                result[k.strip()] = _parse_value(v.strip())

    # Fermer la dernière liste
    if in_list:
        if current_dict:
            current_list.append(current_dict)
        result["steps"] = current_list

    return result


def _parse_value(v: str):
    """Parse une valeur YAML simple."""
    v = v.strip()
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.isdigit():
        return int(v)
    try:
        return float(v)
    except ValueError:
        pass
    return v.strip("'\"")


def pipeline_to_plan(pipeline: PipelineDef, workdir: str = ".") -> PipelinePlan:
    """Convertit une définition de pipeline en PipelinePlan pour meta-harness."""
    harness = MetaHarness(workdir=workdir)
    agent_names = [s.agent for s in pipeline.steps if s.agent]
    plan = harness.plan(agent_names)

    # Mettre à jour les descriptions des steps avec les noms YAML
    for step, yaml_step in zip(plan.steps, pipeline.steps):
        if yaml_step.name:
            step.agent = yaml_step.name
        if yaml_step.on_fail == "block":
            step.agent += " 🔒"  # marquer comme bloquant

    return plan


def run_pipeline(pipeline: PipelineDef, workdir: str = ".") -> dict:
    """Exécute un pipeline YAML via le meta-harness."""
    harness = MetaHarness(workdir=workdir)
    plan = pipeline_to_plan(pipeline, workdir)

    print(f"📋 Pipeline: {pipeline.name}")
    print(f"   Description: {pipeline.description}")
    print(f"   Steps: {[s.agent for s in plan.steps]}")
    print()

    session = harness.execute(plan)
    result = {
        "pipeline": pipeline.name,
        "steps": len(plan.steps),
        "passed": sum(1 for r in session.results if r.status == "passed"),
        "failed": sum(1 for r in session.results if r.status == "failed"),
        "skipped": sum(1 for r in session.results if r.status == "skipped"),
    }

    print(session.report())
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pipeline_dsl", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run", help="Run a pipeline from YAML file or built-in name")
    s.add_argument("pipeline", help="Path to .yaml file or built-in name")
    s.add_argument("--workdir", default=".", help="Project root")

    s = sub.add_parser("validate", help="Validate a YAML pipeline file")
    s.add_argument("file", help="Path to .yaml file")

    sub.add_parser("list", help="List available built-in pipelines")

    args = p.parse_args(argv)

    if args.cmd == "list":
        print("Built-in pipelines:")
        for name, pipe in _BUILTIN_PIPELINES.items():
            steps = ", ".join(s["agent"] for s in pipe["steps"])
            print(f"  📋 {name:<20} {pipe['description']}")
            print(f"     Steps: {steps}")
        print()
        print("Custom: python -m skills.meta_harness.pipeline_dsl run mon_pipeline.yaml")
        return 0

    elif args.cmd == "validate":
        path = Path(args.file)
        if not path.exists():
            print(f"❌ File not found: {path}")
            return 1
        try:
            text = path.read_text()
            pipeline = parse_yaml(text)
            if pipeline and pipeline.steps:
                print(f"✅ Valid pipeline: {pipeline.name} ({len(pipeline.steps)} steps)")
                for s in pipeline.steps:
                    print(f"   - {s.name:20} agent={s.agent}")
                return 0
            else:
                print(f"❌ Invalid pipeline: no steps or missing name")
                return 1
        except Exception as e:
            print(f"❌ Parse error: {e}")
            return 1

    elif args.cmd == "run":
        # Check if it's a built-in name
        if args.pipeline in _BUILTIN_PIPELINES:
            data = _BUILTIN_PIPELINES[args.pipeline]
            pipe = PipelineDef(name=data["name"], description=data.get("description", ""),
                               steps=[PipelineStep(**s) for s in data["steps"]])
        else:
            path = Path(args.pipeline)
            if not path.exists():
                print(f"❌ File not found: {path}")
                print(f"   Available built-ins: {', '.join(_BUILTIN_PIPELINES.keys())}")
                return 1
            text = path.read_text()
            pipe = parse_yaml(text)
            if not pipe:
                print(f"❌ Failed to parse {path}")
                return 1

        run_pipeline(pipe, workdir=args.workdir)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
