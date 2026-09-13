"""Compare two trusted finder checkouts on a frozen selection corpus.

Preview is offline. Execution reuses LocalLLMClient and Conductor checkpoints.
The benchmark never executes a selected operation or promotes a candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATTERNS = ("*.py", "skills/**/SKILL.md", "skills/**/effects.json")
OBSERVATION_FIELDS = {"job_sha256", "paths", "shortlist", "review_status", "review_reason", "tier", "measurements"}
ACCEPTANCE_POLICY = "exact-selection-and-abstention/v1"


class BenchmarkInputError(ValueError):
    """A fixed, safe diagnostic that contains no endpoint or prompt text."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(repo):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])
    paths = git("ls-files", "-z", "--", *SOURCE_PATTERNS).decode("utf-8").split("\0")
    hashes = {p: file_hash(repo / p) for p in paths if p}
    if "skills/skill_finder/finder.py" not in hashes:
        raise ValueError("checkout has no tracked skill finder")
    return {"head": git("rev-parse", "HEAD").decode().strip(),
            "code_sha256": digest(hashes), "source_count": len(hashes),
            "sources_match_commit": not bool(git("diff", "--name-only", "HEAD", "--", *SOURCE_PATTERNS).strip()),
            "source_scope": list(SOURCE_PATTERNS)}


def load_corpus(path):
    from skills.conductor.verified import read_document
    data = read_document(path)
    if (not isinstance(data, dict) or data.get("schema") != "botte.skill-selection-cases/v1"
            or data.get("dataset_class") not in {"fixture", "reviewed_holdout"}):
        raise ValueError("unsupported corpus")
    skills, cases = data.get("skills"), data.get("cases")
    if not isinstance(skills, dict) or not 1 <= len(skills) <= 10:
        raise ValueError("corpus needs 1 to 10 skills")
    for key, body in skills.items():
        if (not re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_-]+/SKILL\.md", key)
                or not isinstance(body, str) or not body.strip()):
            raise ValueError("invalid fixture skill")
    if sum(len(body.encode("utf-8")) for body in skills.values()) > 65536:
        raise ValueError("corpus instruction budget exceeded")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 12:
        raise ValueError("corpus needs 1 to 12 cases")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("invalid case object")
        key, expected = case.get("id"), case.get("expected_paths")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_-]{1,40}", key) or key in seen:
            raise ValueError("invalid or duplicate case ID")
        seen.add(key)
        if not isinstance(case.get("task"), str) or not 1 <= len(case["task"]) <= 4000:
            raise ValueError("invalid task")
        if (not isinstance(expected, list) or any(not isinstance(p, str) or p not in skills for p in expected)
                or len(set(expected)) != len(expected) or not isinstance(case.get("rationale"), str)
                or not case["rationale"].strip()):
            raise ValueError("invalid selection oracle")
    if data["dataset_class"] == "reviewed_holdout":
        refs = data.get("review_evidence")
        if not isinstance(refs, list) or not 1 <= len(refs) <= 20 or any(
                not isinstance(ref, str) or not 1 <= len(ref.strip()) <= 256 for ref in refs):
            raise ValueError("holdout requires independent review references")
    return data


def worker(job):
    """One inference, in a fresh process; expected answers are not supplied."""
    repo = Path(job["repo"])
    if snapshot(repo) != job["source"]:
        raise ValueError("source changed before inference")
    sys.path.insert(0, str(repo))
    from skills.skill_finder.finder import find
    from skills.llm_backends.client import LocalLLMClient
    from skills.llm_backends.discovery import Backend
    backend = Backend(**job["backend"])
    measurements = {"calls": 0, "latency_ms": None, "prompt_tokens": None,
                    "completion_tokens": None, "response_model_matches": False,
                    "truncated": False, "prompt_bytes": None}

    class MeasuredClient(LocalLLMClient):
        def _post(self, path, body):
            measurements["calls"] += 1
            measurements["prompt_bytes"] = len(body["messages"][-1]["content"].encode("utf-8"))
            started = time.perf_counter()
            try:
                payload = super()._post(path, body)
            finally:
                measurements["latency_ms"] = (time.perf_counter() - started) * 1000
            measurements["response_model_matches"] = payload.get("model") == job["model"]
            usage = payload.get("usage") or {}
            for key in ("prompt_tokens", "completion_tokens"):
                value = usage.get(key)
                measurements[key] = value if type(value) is int and value >= 0 else None
            return payload

        def chat(self, prompt, **kwargs):
            result = super().chat(prompt, model=job["model"], **kwargs)
            measurements["truncated"] = result.truncated
            return result

    client = MeasuredClient(backend, timeout=job["timeout"])
    with tempfile.TemporaryDirectory(prefix="botte-selection-") as directory:
        root = Path(directory)
        for key, body in job["skills"].items():
            target = root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
        with patch("skills.llm_backends.registry.best_chat_backend", return_value=backend), \
                patch("skills.llm_backends.client.LocalLLMClient", return_value=client):
            lexical = find(job["task"], roots=[root], top_k=5)
            result = find(job["task"], roots=[root], top_k=5, use_local=True)
        normalize = lambda matches: [Path(m["path"]).relative_to(root).as_posix() for m in matches]
        paths, shortlist = normalize(result["matches"]), normalize(lexical["matches"])
    if snapshot(repo) != job["source"]:
        raise ValueError("source changed during inference")
    status = result.get("local_review", {}).get("status", "legacy_unspecified")
    return {"job_sha256": digest(job), "paths": paths, "shortlist": shortlist,
            "review_status": status, "review_reason": result.get("local_review", {}).get("reason"),
            "tier": result["tier"], "measurements": measurements}


def validate_observation(value, job):
    validate_observation_fields(value, job["skills"], digest(job))


def validate_observation_fields(value, skills, expected_job_hash):
    if (not isinstance(value, dict) or set(value) != OBSERVATION_FIELDS
            or value["job_sha256"] != expected_job_hash
            or not isinstance(expected_job_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_job_hash)):
        raise ValueError("invalid observation binding or fields")
    for key in ("paths", "shortlist"):
        paths = value[key]
        if (not isinstance(paths, list) or len(paths) > len(skills)
                or any(not isinstance(p, str) or p not in skills for p in paths)
                or len(set(paths)) != len(paths)):
            raise ValueError("invalid observation paths")
    if not set(value["paths"]) <= set(value["shortlist"]):
        raise ValueError("returned path was not retrieved")
    if (value["review_status"] not in {"selected", "abstained", "unavailable", "legacy_unspecified"}
            or value["tier"] not in {"free-lexical", "local-llm-reranked"}):
        raise ValueError("invalid review state")
    if value["review_status"] in {"selected", "abstained"}:
        if (value["tier"] != "local-llm-reranked"
                or bool(value["paths"]) != (value["review_status"] == "selected")):
            raise ValueError("review state contradicts returned paths")
    if value["review_status"] == "unavailable" and value["tier"] != "free-lexical":
        raise ValueError("unavailable review cannot be reranked")
    reason = value["review_reason"]
    if reason is not None and (not isinstance(reason, str) or not re.fullmatch(r"[a-z_]{1,80}", reason)):
        raise ValueError("invalid review reason")
    metrics = value["measurements"]
    if not isinstance(metrics, dict) or set(metrics) != {"calls", "latency_ms", "prompt_tokens",
            "completion_tokens", "response_model_matches", "truncated", "prompt_bytes"}:
        raise ValueError("invalid measurement fields")
    if type(metrics["calls"]) is not int or metrics["calls"] < 0:
        raise ValueError("invalid call count")
    for key in ("response_model_matches", "truncated"):
        if type(metrics[key]) is not bool:
            raise ValueError("invalid measurement flag")
    for key in ("latency_ms", "prompt_tokens", "completion_tokens", "prompt_bytes"):
        number = metrics[key]
        types = (int, float) if key == "latency_ms" else (int,)
        if number is not None and (type(number) not in types or not math.isfinite(number) or number < 0):
            raise ValueError("invalid numeric measurement")


def assess_selection(report, corpus):
    """Recompute a conservative review boundary; never authorize an operation.

    The caller supplies trusted observations. An offline file hash binds bytes,
    not the truth of a model identity, oracle or remote execution claim.
    """
    if (not isinstance(report, dict) or report.get("schema") != "botte.skill-selection-comparison/v1"
            or report.get("dataset_class") != corpus["dataset_class"]
            or report.get("corpus_sha256") != digest(corpus)
            or report.get("status") not in {"measurement_complete", "insufficient_evidence"}
            or not isinstance(report.get("gaps"), list)):
        raise ValueError("assessment report or corpus mismatch")
    cases = {case["id"]: set(case["expected_paths"]) for case in corpus["cases"]}
    planned, started = report.get("planned_calls"), report.get("attempts_started")
    if (type(planned) is not int or planned % (2 * len(cases))
            or not 1 <= planned // (2 * len(cases)) <= 3
            or type(started) is not int or not 0 <= started <= planned
            or not isinstance(report.get("observations"), list)
            or len(report["observations"]) > started):
        raise ValueError("invalid assessment coverage")
    repeats = planned // (2 * len(cases))
    expected_jobs = {f"r{repeat}-{case}-{side}": (case, repeat, side)
                     for repeat in range(repeats) for case in cases for side in ("baseline", "candidate")}
    rows, exact, metric_gaps = {}, {}, []
    for row in report["observations"]:
        if not isinstance(row, dict) or not isinstance(row.get("job"), str):
            raise ValueError("invalid assessment row")
        key = row["job"]
        if (key not in expected_jobs or key in rows or type(row.get("repeat")) is not int
                or (row.get("case_id"), row["repeat"], row.get("side")) != expected_jobs[key]):
            raise ValueError("duplicate or mispaired assessment row")
        observation = {field: row[field] for field in OBSERVATION_FIELDS}
        validate_observation_fields(observation, corpus["skills"], row["job_sha256"])
        measure = row["measurements"]
        comparable = measure["calls"] == 1 and measure["response_model_matches"] and not measure["truncated"]
        if not comparable or any(measure[k] is None for k in ("latency_ms", "prompt_tokens", "completion_tokens")):
            metric_gaps.append(key)
        available = row["tier"] == "local-llm-reranked" and row["review_status"] != "unavailable"
        # Recompute from paths and flags: stored totals and exact_selection are not an oracle.
        exact[key] = comparable and available and set(row["paths"]) == cases[row["case_id"]]
        rows[key] = row
    failures, excluded, new_excluded, lost_exact, lost_paths = [], [], [], [], []
    totals = {side: {"observed": 0, "exact": 0, "positive_exact": 0, "correct_abstentions": 0,
                     "negative_with_selection": 0, "lexical_fallback": 0}
              for side in ("baseline", "candidate")}
    for key, row in rows.items():
        expected, actual = cases[row["case_id"]], set(row["paths"])
        total = totals[row["side"]]
        total["observed"] += 1
        total["exact"] += int(exact[key])
        total["positive_exact"] += int(bool(expected) and exact[key])
        total["correct_abstentions"] += int(not expected and exact[key])
        total["negative_with_selection"] += int(not expected and bool(actual))
        total["lexical_fallback"] += int(row["tier"] == "free-lexical")
        if row["side"] != "candidate":
            continue
        baseline_key = f"r{row['repeat']}-{row['case_id']}-baseline"
        baseline = rows.get(baseline_key)
        if not exact[key]:
            failures.append(key)
        if not expected and actual:
            excluded.append(key)
            if baseline is not None and not baseline["paths"]:
                new_excluded.append(key)
        if baseline is not None:
            if exact[baseline_key] and not exact[key]:
                lost_exact.append(key)
            missing = (set(baseline["paths"]) & expected) - actual
            if missing:
                lost_paths.append({"job": key, "paths": sorted(missing)})
    missing_jobs = sorted(set(expected_jobs) - set(rows))
    coverage_gaps = [label for label, present in (
        ("no_positive_cases", any(cases.values())), ("no_negative_cases", any(not v for v in cases.values()))) if not present]
    incomplete = (missing_jobs or metric_gaps or report["gaps"] or started != planned
                  or report["status"] != "measurement_complete")
    if incomplete:
        state, decision = "insufficient_evidence", "reconcile_run"
    elif failures or lost_paths:
        state, decision = "not_accepted", "do_not_promote"
    elif coverage_gaps:
        state, decision = "insufficient_evidence", "collect_representative_cases"
    elif corpus["dataset_class"] == "fixture":
        state, decision = "fixture_only", "collect_held_out_evidence"
    else:
        state, decision = "review_required", "review_results"
    return {"policy": ACCEPTANCE_POLICY, "state": state, "decision": decision,
            "automatic_promotion": False, "operation_quality": "unmeasured",
            "counts_are_repeated_observations": True, "repetitions": repeats, "totals": totals,
            "candidate_failures": sorted(failures), "candidate_excluded_selections": sorted(excluded),
            "new_excluded_selections": sorted(new_excluded), "lost_reviewed_selections": sorted(lost_exact),
            "lost_required_paths": sorted(lost_paths, key=lambda item: item["job"]),
            "missing_jobs": missing_jobs, "metric_gaps": sorted(metric_gaps),
            "reported_evidence_gaps": bool(report["gaps"]), "coverage_gaps": coverage_gaps}


def assess_file(path, expected_sha256, corpus):
    """Read one pinned report, without contacting a backend or changing a run."""
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise BenchmarkInputError("offline assessment needs the expected report SHA-256")
    with path.open("rb") as handle:
        raw = handle.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise BenchmarkInputError("report size or SHA-256 mismatch")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    report = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    assessment = assess_selection(report, corpus)
    sources = {side: {key: report["sources"][side][key] for key in ("head", "code_sha256")}
               for side in ("baseline", "candidate")}
    for source in sources.values():
        for key, size in (("head", 40), ("code_sha256", 64)):
            if not isinstance(source[key], str) or not re.fullmatch(f"[0-9a-f]{{{size}}}", source[key]):
                raise ValueError("invalid measured source identity")
    return {"schema": "botte.skill-selection-assessment/v1", "status": "assessed",
            "assessment_harness_sha256": file_hash(__file__), "report_sha256": expected_sha256,
            "corpus_sha256": digest(corpus), "dataset_class": corpus["dataset_class"],
            "measured_sources": sources, "acceptance": assessment,
            "inference_calls": 0, "automatic_promotion": False,
            "evidence_scope": "Pinned comparison bytes and corpus; no renewed checkpoint, runtime or model attestation."}


def exit_code(report):
    assessment = report.get("acceptance", {})
    if report["status"] == "insufficient_evidence" or assessment.get("state") == "insufficient_evidence":
        return 3
    return 4 if assessment.get("state") == "not_accepted" else 0


def make_spec(args, corpus):
    from skills.llm_backends import registry
    if not 1 <= args.repetitions <= 3 or not 1 <= args.timeout <= 300:
        raise ValueError("repetitions must be 1..3; timeout must be 1..300 seconds")
    backend = None
    if args.execute:
        if not all((args.registry, args.backend, args.model, args.runtime_id)):
            raise BenchmarkInputError("execution needs registry, backend label, model and runtime-id")
        selected = [b for b in registry.load(args.registry) if b.label == args.backend and b.chat]
        if len(selected) != 1 or args.model not in selected[0].models:
            raise BenchmarkInputError("backend label must resolve uniquely and advertise the explicit model")
        backend = selected[0].to_dict()
    repos = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    spec = {"schema": "botte.skill-selection-run/v1", "corpus_sha256": digest(corpus),
            "dataset_class": corpus["dataset_class"], "harness_sha256": file_hash(__file__),
            "sources": {side: snapshot(repo) for side, repo in repos.items()},
            "runtime_sha256": digest({"backend": backend, "model": args.model,
                                      "runtime_id": args.runtime_id, "python": sys.version}),
            "jobs": {}}
    for repeat in range(args.repetitions):
        for index, case in enumerate(corpus["cases"]):
            order = ("baseline", "candidate") if (repeat + index) % 2 == 0 else ("candidate", "baseline")
            for side in order:
                key = f"r{repeat}-{case['id']}-{side}"
                spec["jobs"][key] = {"repo": str(repos[side]), "source": spec["sources"][side],
                    "task": case["task"], "skills": corpus["skills"], "backend": backend,
                    "model": args.model, "timeout": args.timeout, "side": side,
                    "case_id": case["id"], "repeat": repeat}
    return spec


def make_plan(spec):
    from skills.conductor.verified import validate_plan
    plan = {"schema": "botte.skill-plan/v1", "goal": "Compare skill selection without executing operations",
            "context": digest(spec), "steps": []}
    for key, job in spec["jobs"].items():
        plan["steps"].append({"id": key, "capability": "skill_finder", "command": key,
            "local": True, "needs": [], "requires": [], "observes": [],
            "source_hashes": {"manifest.json": digest_file_bytes(spec)},
            "ensures": [{"kind": "json_equals", "path": f"results/{key}.json",
                         "pointer": "/job_sha256", "value": digest(job)}]})
    validate_plan(plan)
    return plan


def digest_file_bytes(value):
    # Same serialization as atomic_json.write_json(indent=2), including UTF-8.
    return hashlib.sha256(json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")).hexdigest()


def summarize(spec, corpus, execution, output):
    """Consume only checkpoint-verified, unmodified observation files."""
    cases = {case["id"]: case for case in corpus["cases"]}
    rows, gaps = [], []
    for state in execution.get("results", []):
        key = state["id"]
        path = f"results/{key}.json"
        if (state["status"] != "verified" or not (output / path).is_file()
                or file_hash(output / path) != state.get("after", {}).get(path, {}).get("sha256")):
            gaps.append({"job": key, "reason": "unresolved_or_changed_observation"})
            continue
        job = spec["jobs"][key]
        try:
            observation = json.loads((output / path).read_text(encoding="utf-8"))
            validate_observation(observation, job)
        except (ValueError, TypeError, KeyError):
            gaps.append({"job": key, "reason": "invalid_observation"})
            continue
        expected, actual = set(cases[job["case_id"]]["expected_paths"]), set(observation["paths"])
        measure = observation["measurements"]
        review_available = observation["tier"] == "local-llm-reranked" and observation["review_status"] != "unavailable"
        comparable = measure["calls"] == 1 and measure["response_model_matches"] and not measure["truncated"]
        if not comparable or any(measure[k] is None for k in ("latency_ms", "prompt_tokens", "completion_tokens")):
            gaps.append({"job": key, "reason": "incomplete_model_or_cost_evidence"})
        rows.append({"job": key, "side": job["side"], "case_id": job["case_id"], "repeat": job["repeat"],
                     "exact_selection": comparable and review_available and actual == expected,
                     "false_selections": len(actual - expected),
                     "required_candidates_retrieved": expected <= set(observation["shortlist"]),
                     **observation})
    totals = {}
    for side in ("baseline", "candidate"):
        group = [row for row in rows if row["side"] == side]
        latencies = sorted(row["measurements"]["latency_ms"] for row in group
                           if row["measurements"]["latency_ms"] is not None)
        totals[side] = {"observed": len(group), "exact_selections": sum(r["exact_selection"] for r in group),
                       "false_selections": sum(r["false_selections"] for r in group),
                       "latency_p95_ms": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None}
        for token in ("prompt_tokens", "completion_tokens"):
            values = [r["measurements"][token] for r in group]
            planned = sum(job["side"] == side for job in spec["jobs"].values())
            totals[side][token] = sum(values) if len(values) == planned and all(v is not None for v in values) else None
    complete = len(rows) == len(spec["jobs"]) and not gaps
    report = {"schema": "botte.skill-selection-comparison/v1",
            "status": "measurement_complete" if complete else "insufficient_evidence",
            "dataset_class": corpus["dataset_class"], "corpus_sha256": spec["corpus_sha256"],
            "harness_sha256": spec["harness_sha256"], "sources": spec["sources"],
            "runtime_sha256": spec["runtime_sha256"], "totals": totals, "observations": rows,
            "gaps": gaps, "planned_calls": len(spec["jobs"]),
            "attempts_started": sum(row["started"] for row in execution.get("results", [])),
            "automatic_promotion": False,
            "operation_quality": "unmeasured", "energy_kwh": None, "monetary_cost": None}
    report["acceptance"] = assess_selection(report, corpus)
    report["decision"] = report["acceptance"]["decision"]
    return report


def run(spec, corpus, output, *, resume=False):
    from skills.atomic_json import write_json
    from skills.conductor.verified import execute_verified, read_document
    output = output.resolve()
    plan = make_plan(spec)
    if resume:
        if read_document(output / "manifest.json") != spec:
            raise BenchmarkInputError("resume context changed; reconcile the existing run")
    else:
        output.mkdir(parents=True, exist_ok=False)
        write_json(output / "manifest.json", spec)
        write_json(output / "plan.json", plan)

    def dispatch(command, cwd, timeout):
        job = spec["jobs"][command]
        target = output / "results" / f"{command}.json"
        if target.exists():
            return -1, "existing observation requires reconciliation"
        try:
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker"],
                input=json.dumps(job), cwd=job["repo"], env={**os.environ, "PYTHONPATH": job["repo"]},
                capture_output=True, text=True, encoding="utf-8", timeout=timeout)
            if proc.returncode:
                return -1, "worker failed; remote completion is unknown"
            result = json.loads(proc.stdout)
            validate_observation(result, job)
            write_json(target, result)
            return 0, "observation recorded; operation quality unmeasured"
        except (subprocess.TimeoutExpired, OSError, ValueError, KeyError, TypeError):
            return -1, "inference or capture incomplete; reconcile before retry"

    execution = execute_verified(plan, cwd=str(output), confirm=True, checkpoint="checkpoint.json",
                                 resume=resume, timeout=max(j["timeout"] for j in spec["jobs"].values()) + 15,
                                 runner=dispatch)
    if "error" in execution:
        raise ValueError(execution["error"])
    report = summarize(spec, corpus, execution, output)
    write_json(output / "comparison.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path, default=ROOT)
    parser.add_argument("--corpus", type=Path, default=ROOT / "docs/examples/skill-selection-cases.json")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--backend")
    parser.add_argument("--model")
    parser.add_argument("--runtime-id")
    parser.add_argument("--output", type=Path, default=Path("reports/skill-selection"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--assess", type=Path, help="assess a pinned existing comparison without inference")
    parser.add_argument("--report-sha256", help="expected SHA-256 of the complete comparison file")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.worker:
            print(json.dumps(worker(json.load(sys.stdin)), ensure_ascii=False))
            return 0
        sys.path.insert(0, str(ROOT))
        if args.assess is not None:
            if (any((args.execute, args.resume, args.baseline, args.registry, args.backend, args.model, args.runtime_id))
                    or args.repetitions != 1 or args.timeout != 90 or args.output != Path("reports/skill-selection")):
                raise BenchmarkInputError("offline assessment cannot be combined with execution inputs")
            report = assess_file(args.assess, args.report_sha256, load_corpus(args.corpus))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return exit_code(report)
        if args.report_sha256 is not None:
            raise BenchmarkInputError("report SHA-256 requires offline assessment")
        if args.baseline is None or (args.resume and not args.execute):
            raise BenchmarkInputError("baseline required; resume requires execute")
        corpus = load_corpus(args.corpus)
        spec = make_spec(args, corpus)
        make_plan(spec)
        if args.execute:
            report = run(spec, corpus, args.output, resume=args.resume)
        else:
            report = {"status": "prepared", "dataset_class": corpus["dataset_class"],
                      "cases": len(corpus["cases"]), "planned_calls": len(spec["jobs"]),
                      "sources": spec["sources"], "corpus_sha256": spec["corpus_sha256"],
                      "harness_sha256": spec["harness_sha256"], "inference_calls": 0,
                      "quality": "unmeasured", "local_cost": None, "automatic_promotion": False}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code(report)
    except BenchmarkInputError as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        # Raw exceptions may contain private endpoints, prompts or server replies.
        print(json.dumps({"status": "blocked", "reason": "invalid_input_or_unresolved_run"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
