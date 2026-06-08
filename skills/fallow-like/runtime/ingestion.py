"""Runtime data ingestion for hot path analysis."""

from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel
import json


class RuntimeData(BaseModel):
    call_counts: dict[str, int] = {}
    latencies: dict[str, float] = {}
    p99_latencies: dict[str, float] = {}
    error_rates: dict[str, float] = {}
    timestamps: list[str] = []


class RuntimeIngestion:
    @staticmethod
    def from_json(path: Path) -> RuntimeData:
        data = json.loads(path.read_text())
        return RuntimeData(**data)

    @staticmethod
    def from_prometheus_metrics(text: str) -> RuntimeData:
        call_counts: dict[str, int] = {}
        latencies: dict[str, float] = {}
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0].strip("{}")
                try:
                    value = float(parts[1])
                    if "count" in name:
                        call_counts[name] = int(value)
                    elif "latency" in name or "duration" in name:
                        latencies[name] = value
                except ValueError:
                    continue
        return RuntimeData(call_counts=call_counts, latencies=latencies)

    @staticmethod
    def merge(*datasets: RuntimeData) -> RuntimeData:
        merged = RuntimeData()
        for ds in datasets:
            for k, v in ds.call_counts.items():
                merged.call_counts[k] = merged.call_counts.get(k, 0) + v
            for k, v in ds.latencies.items():
                merged.latencies[k] = (merged.latencies.get(k, 0) + v) / 2
        return merged
