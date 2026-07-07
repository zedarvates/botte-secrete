"""
Hook for context_profiler — integrate AutoMemory into the control loop.
"""

from typing import Any
from skills.auto_memory.memory_bank import MemoryBank
from skills.auto_memory.trajectory import TrajectoryRecorder
from skills.auto_memory.compressor import compress_memories, bottleneck_compress

_memory_bank: MemoryBank | None = None
_trajectory: TrajectoryRecorder | None = None


def init_memory(task_id: str | None = None):
    """Initialize memory for the current session."""
    global _memory_bank, _trajectory
    _memory_bank = MemoryBank()
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


def store_memory(key: str, value: Any, category: str = "fact", confidence: float = 1.0):
    """Store a memory entry."""
    if _memory_bank:
        _memory_bank.store(key, value, category, confidence)


def recall_memory(key: str, default: Any = None) -> Any:
    """Retrieve a memory entry."""
    if _memory_bank:
        return _memory_bank.recall(key, default)
    return default


def consolidate_memory():
    """Merge similar memories."""
    if _memory_bank:
        compress_memories(_memory_bank)


def reduce_memory(keep_pct: float = 0.3) -> int:
    """Reduce memory to top entries."""
    if _memory_bank:
        return bottleneck_compress(_memory_bank, keep_pct)
    return 0


def memory_stats() -> dict:
    """Return memory bank statistics."""
    if _memory_bank:
        return _memory_bank.stats()
    return {"total_entries": 0, "by_category": {}, "total_accesses": 0}