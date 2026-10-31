"""AutoMemory — Memory as a learnable skill for botte-secrete."""
from skills.auto_memory.memory_bank import MemoryBank, MemoryEntry
from skills.auto_memory.trajectory import TrajectoryRecorder
from skills.auto_memory.compressor import compress_memories, extract_patterns, bottleneck_compress
from skills.auto_memory.hook import (
    init_memory, record_step, save_trajectory,
    store_memory, store_external_memory, recall_memory, inspect_memory,
    consolidate_memory, reduce_memory, memory_stats,
)

__all__ = [
    "MemoryBank", "MemoryEntry", "TrajectoryRecorder",
    "compress_memories", "extract_patterns", "bottleneck_compress",
    "init_memory", "record_step", "save_trajectory",
    "store_memory", "store_external_memory", "recall_memory", "inspect_memory",
    "consolidate_memory", "reduce_memory", "memory_stats",
]
