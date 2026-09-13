"""Compare selection protocol handling in two trusted local checkouts.

Model replies are injected. This measures no model accuracy or inference cost.
Only temporary fixture files are written; the report is printed to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


BOUND_SOURCES = (
    "skills/skill_finder/finder.py", "skills/skill_finder/__init__.py",
    "skills/skill_finder/SKILL.md", "skills/llm_backends/client.py",
    "skills/llm_backends/registry.py",
)


def fingerprint(repo: Path) -> dict:
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
            for name in BOUND_SOURCES}


def worker(repo: Path) -> dict:
    sys.path.insert(0, str(repo))
    before = fingerprint(repo)
    from skills.skill_finder.finder import find

    cases = []
    with tempfile.TemporaryDirectory(prefix="botte-review-replay-") as directory:
        root = Path(directory)
        bodies = []
        for vendor, mode in (("a", "private notes"), ("b", "shared observations")):
            path = root / vendor / "memory" / "SKILL.md"
            path.parent.mkdir(parents=True)
            body = ("---\nname: memory\ndescription: Inspect memory records.\n---\n"
                    f"Read {mode}. Exclude deletion. Require an authorized project.\n")
            path.write_text(body, encoding="utf-8")
            bodies.append(body)
        a, b = "a/memory/SKILL.md", "b/memory/SKILL.md"
        for case_id, answer, expected in (
            ("retain_second_only", "2", [b]),
            ("respect_reverse_order", "2,1", [b, a]),
            ("explicit_abstention", "0", []),
        ):
            with patch("skills.llm_backends.registry.best_chat_backend", return_value=True), \
                    patch("skills.llm_backends.client.LocalLLMClient") as client:
                client.return_value.chat.return_value = SimpleNamespace(text=answer)
                result = find("inspect memory", roots=[root], use_local=True)
                prompt = client.return_value.chat.call_args.args[0]
            actual = [Path(m["path"]).relative_to(root).as_posix() for m in result["matches"]]
            # New prompts encode full bodies as JSON strings; the old prompt
            # includes shortened descriptions. No semantic model judgment here.
            full_bodies = all(json.dumps(body, ensure_ascii=False) in prompt for body in bodies)
            cases.append({"id": case_id, "injected_reply": answer,
                          "expected_paths": expected, "observed_paths": actual,
                          "path_contract_passed": actual == expected,
                          "full_skill_bodies_attached": full_bodies,
                          "prompt_bytes": len(prompt.encode("utf-8"))})
    after = fingerprint(repo)
    if before != after:
        raise RuntimeError("Sources changed during replay; discard this comparison")
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    matches_commit = True
    for name, digest in before.items():
        data = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{name}"],
                              capture_output=True, check=True).stdout
        matches_commit &= hashlib.sha256(data).hexdigest() == digest
    return {"checkout_head": commit, "sources_match_commit": matches_commit,
            "source_sha256": before, "cases": cases,
            "path_contract_passed": sum(c["path_contract_passed"] for c in cases),
            "full_body_delivery_passed": sum(c["full_skill_bodies_attached"] for c in cases)}


def probe(repo: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker", "--candidate", str(repo)],
        cwd=repo, env={**os.environ, "PYTHONPATH": str(repo)},
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.candidate.resolve()), ensure_ascii=False))
        return 0
    if args.baseline is None:
        parser.error("--baseline must name a trusted local checkout")
    baseline, candidate = probe(args.baseline.resolve()), probe(args.candidate.resolve())
    report = {"schema": "botte.skill-review-replay/v1",
              "scope": "injected_reply_protocol_only", "python": sys.version.split()[0],
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "baseline": baseline, "candidate": candidate,
              "real_model_evaluated": False, "local_inference_cost": None,
              "representative_task_quality": "unmeasured", "automatic_promotion": False}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(c["path_contract_passed"] and c["full_skill_bodies_attached"]
                    for c in candidate["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
