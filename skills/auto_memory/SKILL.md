---
name: auto-memory
description: "Memory as a learnable skill — store, recall, compress, and consolidate agent memories. Inspired by Stanford AutoMem."
version: 1.0.0
---

# AutoMemory

Memory as a capability, not just storage. Adapts to patterns in agent behavior.

## Features

- **MemoryBank** — persistent key/value store with categories and confidence scores
- **TrajectoryRecorder** — capture goal→actions→outcomes paths
- **Compressor** — deduplicate, bottleneck reduction, pattern extraction
- **Hook** — integrate with context_profiler and control loop

## Usage

```python
from skills.auto_memory import init_memory, store_memory, recall_memory

bank = init_memory()
store_memory("user_pref.format", "concise", category="user_pref", confidence=0.95)
prefs = recall_memory("user_pref.format")
```

## Integration

Add to `control_loop.py`:

```python
from skills.auto_memory.hook import init_memory, record_step, consolidate_memory

bank = init_memory("task_123")
record_step("plan", {"steps": ["a", "b"]})
consolidate_memory()  # merge similar memories
```