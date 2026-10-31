"""Translate GitHub Actions step outcomes into bounded QA envelopes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from skills.atomic_json import write_json
from skills.trajectory.outcome import emit_outcome

PUBLIC_SCHEMA = "botte.ci-outcome-public/v1"
STEP_OUTCOMES = ("success", "failure", "cancelled", "skipped")


def _step(value: object, name: str) -> str:
    if not isinstance(value, str) or value.casefold() not in STEP_OUTCOMES:
        raise ValueError(f"{name} must be one of: {', '.join(STEP_OUTCOMES)}")
    return value.casefold()


def _classification(tests: str, docs: str) -> tuple[str, str, str]:
    observed = {tests, docs}
    if "failure" in observed:
        return "FAIL", "failing", "Inspect the failing CI step before merge."
    if "cancelled" in observed:
        return "UNCERTAIN", "uncertain", "Inspect or rerun the cancelled CI job."
    if observed == {"success"}:
        return "PASS_ROBUST", "grounded", "No action; retain SHADOW authority."
    return "PARTIAL", "collecting", "Run every required CI step before drawing a conclusion."


def emit_ci_outcome(*, tests_outcome: str, docs_outcome: str,
                    run_id: str, run_attempt: str, job: str,
                    python_version: str, project_root: str | Path = ".",
                    public_output: str | Path | None = None) -> dict:
    """Emit a private verified CI fact and an optional sanitized public summary."""
    tests = _step(tests_outcome, "tests_outcome")
    docs = _step(docs_outcome, "docs_outcome")
    values = {
        "run_id": run_id, "run_attempt": run_attempt,
        "job": job, "python_version": python_version,
    }
    for name, value in values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    status, state, next_action = _classification(tests, docs)
    identity = "\n".join(value.strip() for value in values.values())
    execution_id = "ci-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    evidence = (
        f"github-actions:run:{run_id}:python:{python_version}:tests:{tests}",
        f"github-actions:run:{run_id}:python:{python_version}:docs:{docs}",
    )
    result = emit_outcome(
        "repository CI verification",
        project_root=project_root,
        execution_id=execution_id,
        source="ci",
        route="deterministic",
        status=status,
        verified_by="ci:github-actions",
        evidence_refs=evidence,
        task_type="repository_validation",
        tags=("ci", f"python-{python_version}"),
        harness="github-actions",
        tool_versions={"python": python_version, "workflow": "ci-v1"},
        acted=True,
    )
    envelope = result["envelope"]
    public = {
        "schema": PUBLIC_SCHEMA,
        "outcome_id": envelope["id"],
        "state": state,
        "reason": (
            "Required repository tests and documentation checks passed."
            if state == "grounded" else
            "At least one required CI step failed."
            if state == "failing" else
            "CI did not observe every required step as successful."
        ),
        "next_safe_action": next_action,
        "status": status,
        "verified": bool(envelope["verified"]),
        "evidence_count": len(evidence),
        "shadow_only": True,
        "activation_allowed": False,
        "privacy": {
            "raw_task": False,
            "execution_fingerprint": False,
            "local_path": False,
            "evidence_detail": False,
        },
    }
    if public_output is not None:
        write_json(public_output, public)
    return {**result, "public": public}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", required=True, choices=STEP_OUTCOMES)
    parser.add_argument("--docs", required=True, choices=STEP_OUTCOMES)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--project", default=".")
    parser.add_argument("--public-output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = emit_ci_outcome(
        tests_outcome=args.tests,
        docs_outcome=args.docs,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        job=args.job,
        python_version=args.python_version,
        project_root=args.project,
        public_output=args.public_output,
    )
    if args.json:
        print(json.dumps(result["public"], ensure_ascii=False, indent=2))
    else:
        public = result["public"]
        print(f"CI QA: {public['state']} · {public['reason']}")
        print(f"Next: {public['next_safe_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["PUBLIC_SCHEMA", "STEP_OUTCOMES", "emit_ci_outcome"]
