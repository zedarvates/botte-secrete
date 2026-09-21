"""Comparable, privacy-preserving benchmark for local LLM workers.

The runner talks to an already-running OpenAI-compatible endpoint.  It never
downloads a model, changes drivers, or promotes a worker.  Prompts and raw
responses are used in memory only and are deliberately absent from reports.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


PLAN_SCHEMA = "botte.local-worker-benchmark-plan/v1"
MISSION_SCHEMA = "botte.local-worker-benchmark-mission/v1"
REPORT_SCHEMA = "botte.local-worker-benchmark/v1"
ROLES = {"SCOUT", "REQUIREMENTS", "VALIDATOR"}
_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_MODEL_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,255}$")


class BenchmarkInputError(ValueError):
    """The benchmark input is unsafe, ambiguous, or incomplete."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    model: str
    family: str
    quantization: str
    source_uri: str


@dataclass(frozen=True)
class Mission:
    id: str
    family: str
    role: str
    system: str
    prompt: str
    expected: dict[str, Any]
    tools: tuple[dict[str, Any], ...] = ()


@dataclass
class Observation:
    content: str = ""
    tool_names: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ttft_ms: float | None = None
    duration_ms: float | None = None
    error_code: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise BenchmarkInputError(f"{label} must be a bounded opaque identifier")
    return value


def _require_model_ref(value: Any) -> str:
    if not isinstance(value, str) or not _MODEL_REF.fullmatch(value) or ".." in value:
        raise BenchmarkInputError("runtime model must be a safe model name or tag")
    return value


def _require_source(value: Any) -> str:
    source = str(value)
    if source.startswith("https://") and len(source) <= 512:
        parsed = urllib.parse.urlparse(source)
        if parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment:
            return source
    if source.startswith("local:") and _SAFE_ID.fullmatch(source[6:]):
        return source
    raise BenchmarkInputError("source_uri must be HTTPS or an opaque local identifier")


def _private_endpoint(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BenchmarkInputError("endpoint must be an HTTP(S) URL")
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise BenchmarkInputError("endpoint must be an origin without credentials or query data")
    host = parsed.hostname.lower()
    allowed = host in {"localhost", "127.0.0.1", "::1"}
    if not allowed:
        try:
            allowed = ipaddress.ip_address(host).is_private
        except ValueError:
            allowed = host.endswith(".local")
    if not allowed:
        raise BenchmarkInputError("local-worker benchmark rejects public endpoints")
    return url.rstrip("/")


def load_plan(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != PLAN_SCHEMA:
        raise BenchmarkInputError(f"plan schema must be {PLAN_SCHEMA}")
    allowed = {
        "schema", "authority", "endpoint", "api_key_env", "models",
        "repetitions", "warmup", "timeout_s", "max_tokens", "temperature",
        "telemetry_interval_s",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise BenchmarkInputError(f"unknown plan fields: {', '.join(unknown)}")
    if raw.get("authority") != "SIMULATE":
        raise BenchmarkInputError("benchmark authority must remain SIMULATE")
    raw["endpoint"] = _private_endpoint(str(raw.get("endpoint", "")))
    models = raw.get("models")
    if not isinstance(models, list) or len(models) < 2:
        raise BenchmarkInputError("at least two local workers are required")
    parsed_models: list[ModelSpec] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict) or set(item) != {
            "id", "model", "family", "quantization", "source_uri"
        }:
            raise BenchmarkInputError("each model needs id/model/family/quantization/source_uri")
        model_id = _require_id(item["id"], "model id")
        if model_id in seen:
            raise BenchmarkInputError("model ids must be unique")
        seen.add(model_id)
        parsed_models.append(ModelSpec(
            id=model_id,
            model=_require_model_ref(item["model"]),
            family=_require_id(item["family"], "model family"),
            quantization=_require_id(item["quantization"], "model quantization"),
            source_uri=_require_source(item["source_uri"]),
        ))
    raw["models"] = parsed_models
    raw["repetitions"] = int(raw.get("repetitions", 1))
    raw["warmup"] = int(raw.get("warmup", 1))
    raw["timeout_s"] = float(raw.get("timeout_s", 180))
    raw["max_tokens"] = int(raw.get("max_tokens", 512))
    raw["temperature"] = float(raw.get("temperature", 0))
    raw["telemetry_interval_s"] = float(raw.get("telemetry_interval_s", 0.25))
    if not 1 <= raw["repetitions"] <= 10 or not 0 <= raw["warmup"] <= 3:
        raise BenchmarkInputError("repetitions/warmup outside safe bounds")
    if not 1 <= raw["timeout_s"] <= 900 or not 1 <= raw["max_tokens"] <= 4096:
        raise BenchmarkInputError("timeout_s/max_tokens outside safe bounds")
    if not 0 <= raw["temperature"] <= 1:
        raise BenchmarkInputError("temperature must be between 0 and 1")
    if not 0.05 <= raw["telemetry_interval_s"] <= 5:
        raise BenchmarkInputError("telemetry_interval_s must be between 0.05 and 5")
    key_env = str(raw.get("api_key_env", ""))
    if key_env and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key_env):
        raise BenchmarkInputError("api_key_env must name an environment variable")
    raw["api_key_env"] = key_env
    return raw


def load_missions(path: str | Path) -> list[Mission]:
    missions: list[Mission] = []
    seen: set[str] = set()
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkInputError(f"mission line {line_no} is invalid JSON") from exc
        allowed = {"schema", "mission_id", "family", "role", "system", "prompt", "expected", "tools", "verified_by", "evidence_ref"}
        if not isinstance(item, dict) or set(item) - allowed:
            raise BenchmarkInputError(f"mission line {line_no} has unknown fields")
        if item.get("schema") != MISSION_SCHEMA:
            raise BenchmarkInputError(f"mission line {line_no} has the wrong schema")
        mission_id = _require_id(item.get("mission_id"), "mission id")
        if mission_id in seen:
            raise BenchmarkInputError("mission ids must be unique")
        seen.add(mission_id)
        role = item.get("role")
        if role not in ROLES:
            raise BenchmarkInputError(f"mission role must be one of {sorted(ROLES)}")
        prompt = item.get("prompt")
        expected = item.get("expected")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
            raise BenchmarkInputError("mission prompt must be non-empty and bounded")
        system = item.get("system", "")
        if not isinstance(system, str) or len(system) > 4000:
            raise BenchmarkInputError("mission system prompt must be a bounded string")
        if not isinstance(expected, dict) or not expected:
            raise BenchmarkInputError("mission expected verdict must be a non-empty object")
        if set(expected) - {"json_subset", "tool_name", "escalate", "validator_verdict"}:
            raise BenchmarkInputError("mission expected verdict has unknown fields")
        if "json_subset" in expected and not isinstance(expected["json_subset"], dict):
            raise BenchmarkInputError("json_subset must be an object")
        if "tool_name" in expected and not _SAFE_ID.fullmatch(str(expected["tool_name"])):
            raise BenchmarkInputError("expected tool_name must be an opaque identifier")
        if "escalate" in expected and not isinstance(expected["escalate"], bool):
            raise BenchmarkInputError("expected escalate must be boolean")
        if "validator_verdict" in expected and expected["validator_verdict"] not in {"PASS", "FAIL", "UNCERTAIN"}:
            raise BenchmarkInputError("validator_verdict must be PASS, FAIL, or UNCERTAIN")
        tools = item.get("tools", [])
        if not isinstance(tools, list) or len(tools) > 8 or len(json.dumps(tools)) > 16000:
            raise BenchmarkInputError("mission tools must be a bounded array")
        for tool in tools:
            function = tool.get("function") if isinstance(tool, dict) else None
            if (not isinstance(function, dict) or tool.get("type") != "function"
                    or not _SAFE_ID.fullmatch(str(function.get("name", "")))
                    or not isinstance(function.get("parameters"), dict)):
                raise BenchmarkInputError("mission tools must use bounded function schemas")
        _require_id(item.get("verified_by"), "verified_by")
        _require_id(item.get("evidence_ref"), "evidence_ref")
        missions.append(Mission(
            id=mission_id,
            family=_require_id(item.get("family"), "mission family"),
            role=role,
            system=system,
            prompt=prompt,
            expected=expected,
            tools=tuple(tools),
        ))
    if not missions:
        raise BenchmarkInputError("at least one mission is required")
    return missions


class HostTelemetry:
    """Best-effort host sampler; absence is reported, never fabricated."""

    def __init__(self, interval_s: float = 0.25):
        self.interval_s = interval_s
        self.peak_ram_bytes: int | None = None
        self.peak_vram_mib: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval_s * 3))

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_ram()
            self._sample_vram()
            self._stop.wait(self.interval_s)

    def _sample_ram(self) -> None:
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0]) * 1024
            used = values["MemTotal"] - values["MemAvailable"]
            self.peak_ram_bytes = max(self.peak_ram_bytes or 0, used)
        except (OSError, ValueError, KeyError):
            pass

    def _sample_vram(self) -> None:
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return
        if proc.returncode:
            return
        for line in proc.stdout.splitlines():
            try:
                gpu, used = [part.strip() for part in line.split(",", 1)]
                self.peak_vram_mib[gpu] = max(self.peak_vram_mib.get(gpu, 0), int(used))
            except (ValueError, TypeError):
                continue


def _stream_openai(plan: dict[str, Any], model: ModelSpec, mission: Mission) -> Observation:
    messages = []
    if mission.system:
        messages.append({"role": "system", "content": mission.system})
    messages.append({"role": "user", "content": mission.prompt})
    body: dict[str, Any] = {
        "model": model.model,
        "messages": messages,
        "temperature": plan["temperature"],
        "max_tokens": plan["max_tokens"],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if mission.tools:
        body["tools"] = list(mission.tools)
    elif "json_subset" in mission.expected or "validator_verdict" in mission.expected:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if plan["api_key_env"]:
        secret = os.environ.get(plan["api_key_env"])
        if not secret:
            return Observation(error_code="API_KEY_UNAVAILABLE")
        headers["Authorization"] = f"Bearer {secret}"
    request = urllib.request.Request(
        plan["endpoint"] + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"), headers=headers, method="POST",
    )
    started = time.perf_counter()
    first = None
    chunks: list[str] = []
    tool_fragments: dict[int, str] = {}
    usage: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=plan["timeout_s"]) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                usage = event.get("usage") or usage
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                for call in delta.get("tool_calls") or []:
                    name = ((call.get("function") or {}).get("name") or "").strip()
                    index = int(call.get("index", 0) or 0)
                    if name:
                        tool_fragments[index] = tool_fragments.get(index, "") + name
                if content or reasoning or tool_fragments:
                    first = first or time.perf_counter()
                chunks.append(content or reasoning)
    except urllib.error.HTTPError as exc:
        return Observation(error_code=f"HTTP_{exc.code}")
    except (urllib.error.URLError, OSError, TimeoutError):
        return Observation(error_code="ENDPOINT_UNAVAILABLE")
    ended = time.perf_counter()
    return Observation(
        content="".join(chunks), tool_names=list(tool_fragments.values()),
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        ttft_ms=round((first - started) * 1000, 3) if first else None,
        duration_ms=round((ended - started) * 1000, 3),
    )


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.strip())
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, AttributeError):
        return None


def _subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _subset(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return expected == actual
    return expected == actual


def score(observation: Observation, mission: Mission) -> dict[str, bool | None]:
    if observation.error_code:
        return {"success": False, "structured": None, "tool": None,
                "escalated": None, "validator_disagreement": None}
    obj = _json_object(observation.content)
    checks: list[bool] = []
    structured = tool = escalated = disagreement = None
    if "json_subset" in mission.expected:
        structured = obj is not None and _subset(mission.expected["json_subset"], obj)
        checks.append(structured)
    if "tool_name" in mission.expected:
        tool = mission.expected["tool_name"] in observation.tool_names
        checks.append(tool)
    if "escalate" in mission.expected:
        escalated = bool(obj and obj.get("escalate") is True)
        checks.append(escalated == bool(mission.expected["escalate"]))
    if "validator_verdict" in mission.expected:
        actual = obj.get("verdict") if obj else None
        disagreement = actual != mission.expected["validator_verdict"]
        checks.append(not disagreement)
    return {"success": bool(checks) and all(checks), "structured": structured,
            "tool": tool, "escalated": escalated, "validator_disagreement": disagreement}


def _percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * proportion + 0.999999)))
    return round(ordered[index], 3)


def _rate(values: Iterable[bool | None]) -> float | None:
    observed = [value for value in values if value is not None]
    return round(sum(bool(value) for value in observed) / len(observed), 4) if observed else None


def _aggregate(rows: list[tuple[Observation, dict[str, bool | None]]], telemetry: HostTelemetry) -> dict[str, Any]:
    completed = [(obs, result) for obs, result in rows if not obs.error_code]
    ttft = [obs.ttft_ms for obs, _ in completed if obs.ttft_ms is not None]
    durations = [obs.duration_ms for obs, _ in completed if obs.duration_ms is not None]
    throughput = [
        obs.completion_tokens / ((obs.duration_ms - (obs.ttft_ms or 0)) / 1000)
        for obs, _ in completed
        if obs.completion_tokens and obs.duration_ms and obs.duration_ms > (obs.ttft_ms or 0)
    ]
    results = [result for _, result in rows]
    error_codes: dict[str, int] = {}
    for obs, _ in rows:
        if obs.error_code:
            error_codes[obs.error_code] = error_codes.get(obs.error_code, 0) + 1
    return {
        "runs": len(rows), "completed": len(completed), "error_codes": error_codes,
        "ttft_ms": {"median": round(statistics.median(ttft), 3) if ttft else None,
                    "p95": _percentile(ttft, 0.95)},
        "duration_ms": {"median": round(statistics.median(durations), 3) if durations else None,
                        "p95": _percentile(durations, 0.95)},
        "throughput_tokens_s": {"median": round(statistics.median(throughput), 3) if throughput else None,
                                "p95": _percentile(throughput, 0.95)},
        "structured_output_validity": _rate(result["structured"] for result in results),
        "tool_call_correctness": _rate(result["tool"] for result in results),
        "mission_success": _rate(result["success"] for result in results),
        "escalation_rate": _rate(result["escalated"] for result in results),
        "validator_disagreement": _rate(result["validator_disagreement"] for result in results),
        "host_ram_used_peak_bytes": telemetry.peak_ram_bytes,
        "gpu_vram_used_peak_mib": telemetry.peak_vram_mib or None,
    }


def run_benchmark(plan_path: str | Path, mission_path: str | Path, *,
                  caller: Callable[[dict[str, Any], ModelSpec, Mission], Observation] = _stream_openai,
                  telemetry_factory: Callable[[float], HostTelemetry] = HostTelemetry) -> dict[str, Any]:
    plan_path, mission_path = Path(plan_path), Path(mission_path)
    plan = load_plan(plan_path)
    missions = load_missions(mission_path)
    models: dict[str, Any] = {}
    missing: list[dict[str, str]] = []
    for model in plan["models"]:
        for mission in missions[:1]:
            for _ in range(plan["warmup"]):
                caller(plan, model, mission)
        telemetry = telemetry_factory(plan["telemetry_interval_s"])
        telemetry.start()
        rows: list[tuple[Observation, dict[str, bool | None]]] = []
        try:
            for _ in range(plan["repetitions"]):
                for mission in missions:
                    observation = caller(plan, model, mission)
                    rows.append((observation, score(observation, mission)))
        finally:
            telemetry.stop()
        metrics = _aggregate(rows, telemetry)
        models[model.id] = {
            "runtime_model": model.model, "family": model.family,
            "quantization": model.quantization, "source_uri": model.source_uri,
            "roles": sorted({mission.role for mission in missions}), "metrics": metrics,
        }
        for metric, value in {
            "TTFT": metrics["ttft_ms"]["median"],
            "throughput": metrics["throughput_tokens_s"]["median"],
            "RAM": metrics["host_ram_used_peak_bytes"],
            "VRAM": metrics["gpu_vram_used_peak_mib"],
        }.items():
            if value is None:
                missing.append({"model_id": model.id, "metric": metric,
                                "reason": "runtime did not expose or host could not sample it"})
        for metric, value in {
            "structured output validity": metrics["structured_output_validity"],
            "tool-call correctness": metrics["tool_call_correctness"],
            "mission success": metrics["mission_success"],
            "escalation rate": metrics["escalation_rate"],
            "validator disagreement": metrics["validator_disagreement"],
        }.items():
            if value is None:
                missing.append({"model_id": model.id, "metric": metric,
                                "reason": "sanitized corpus did not exercise this metric"})
    roles_complete = {mission.role for mission in missions} == ROLES
    if not roles_complete:
        missing.append({"model_id": "dataset", "metric": "role coverage",
                        "reason": "SCOUT, REQUIREMENTS, and VALIDATOR are all required"})
    comparable = all(data["metrics"]["completed"] > 0 for data in models.values())
    comparable = comparable and len(models) >= 2 and roles_complete and not missing
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_status": "measured_comparable" if comparable else "insufficient_evidence",
        "conclusion": ("Comparable observations collected; human review is still required."
                       if comparable else "No promotion decision: complete the missing observations."),
        "dataset": {
            "missions": len(missions), "families": len({m.family for m in missions}),
            "roles": sorted({m.role for m in missions}), "raw_prompts_in_report": False,
            "raw_responses_in_report": False,
        },
        "models": models,
        "missing_metrics": missing,
        "reproducibility": {
            "plan_sha256": _sha256(plan_path), "missions_sha256": _sha256(mission_path),
            "harness_sha256": _sha256(Path(__file__)),
            "repetitions": plan["repetitions"], "warmup": plan["warmup"],
        },
        "authority": {"mode": "SIMULATE", "acted": False, "trained": False,
                      "activation_allowed": False, "builder_promotion_allowed": False},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark existing local workers in SIMULATE mode")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--missions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(args.plan, args.missions)
    except (BenchmarkInputError, json.JSONDecodeError, OSError) as exc:
        print(f"benchmark unavailable: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["benchmark_status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["benchmark_status"] == "measured_comparable" else 3


if __name__ == "__main__":
    raise SystemExit(main())
