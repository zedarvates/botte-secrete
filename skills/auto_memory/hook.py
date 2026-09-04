"""
Hook for context_profiler — integrate AutoMemory into the control loop.
"""

from pathlib import Path
from typing import Any
from skills.auto_memory.memory_bank import MemoryBank, MemoryEntry
from skills.auto_memory.trajectory import TrajectoryRecorder
from skills.auto_memory.compressor import compress_memories, bottleneck_compress

_memory_bank: MemoryBank | None = None
_trajectory: TrajectoryRecorder | None = None


def init_memory(task_id: str | None = None, base_dir: str | Path | None = None):
    """Initialize memory for the current session."""
    global _memory_bank, _trajectory
    _memory_bank = MemoryBank(base_dir=Path(base_dir) if base_dir is not None else None)
    if task_id:
        _trajectory = TrajectoryRecorder(task_id)
    return _memory_bank


def record_step(phase: str, data: dict, outcome: str | None = None, confidence: float = 1.0):
    """Record a trajectory step if trajectory is active."""
    if _trajectory:
        _trajectory.step(phase, data, outcome, confidence)


def save_trajectory():
    """Save the current trajectory."""
    if _trajectory:
        _trajectory.save()


def store_memory(
    key: str,
    value: Any,
    category: str = "fact",
    confidence: float = 1.0,
):
    """Store trusted/local project memory using the legacy-compatible path."""
    if _memory_bank:
        _memory_bank.store(key, value, category, confidence)


def store_external_memory(
    key: str,
    value: Any,
    *,
    source_type: str,
    source_id: str | None = None,
    run_id: str | None = None,
    category: str = "fact",
    confidence: float = 0.5,
    tags: list[str] | None = None,
) -> MemoryEntry | None:
    """Store repo/web/tool/agent/generated input in quarantine.

    Use this hook for text or facts whose origin is outside the trusted local
    project/user path. Normal recall will not surface the entry until an
    explicit review/promotion occurs.
    """
    if not _memory_bank:
        return None
    return _memory_bank.store_external(
        key,
        value,
        source_type=source_type,
        source_id=source_id,
        run_id=run_id,
        category=category,
        confidence=confidence,
        tags=tags,
    )


def recall_memory(key: str, default: Any = None) -> Any:
    """Retrieve trusted/non-quarantined memory only."""
    if _memory_bank:
        return _memory_bank.recall(key, default)
    return default


def inspect_memory(key: str) -> MemoryEntry | None:
    """Inspect memory metadata, including quarantined evidence, without recall."""
    if _memory_bank:
        return _memory_bank.inspect(key)
    return None


def consolidate_memory():
    """Merge similar non-quarantined memories."""
    if _memory_bank:
        compress_memories(_memory_bank)


def reduce_memory(keep_pct: float = 0.3) -> int:
    """Reduce non-quarantined memory to top entries."""
    if _memory_bank:
        return bottleneck_compress(_memory_bank, keep_pct)
    return 0


def memory_stats() -> dict:
    """Return memory bank statistics."""
    if _memory_bank:
        return _memory_bank.stats()
    return {
        "total_entries": 0,
        "quarantined_entries": 0,
        "by_category": {},
        "by_source_type": {},
        "total_accesses": 0,
    }
