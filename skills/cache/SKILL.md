---
name: cache
description: Reuse project scan and audit results through a local ProjectCache, or inspect the in-memory FormCache for approximate prompt matches. Use when repeated analysis may reuse a result after checking source freshness and task context.
---

# Project cache

```python
from skills.cache import ProjectCache

cache = ProjectCache(project_root)
scan = cache.get_or_scan(lambda: scanner.scan())
cache.set_audit_report(report)
```

Read [effects.json](effects.json) for operation-specific consequences. Creating
`ProjectCache` creates `.botte-cache/` even before a lookup. Cache reads can
delete expired, incompatible or fingerprint-mismatched entries, and `get()`
emits a best-effort hit/miss event. A cache miss invokes the supplied scanner;
its effects depend on that callback.

`set()` replaces a JSON entry and adds metadata **to the caller's dictionary**.
Entries contain the unredacted supplied result, project path, timestamp, format
version and metadata fingerprint. Review that data before reuse or sharing.
`invalidate()` deletes one named entry or all JSON entries in the cache directory;
`clear_old()` deletes files older than its age limit (seven days by default).

## Freshness and analysis

The default TTL is 24 hours. When present, the project fingerprint checks relative
paths, file sizes and modification times, excluding internal/cache directories.
It does not hash file contents or bind scanner options, dependency versions or
external state. Entries without a fingerprint can pass the age/version checks.
Concurrent edits or preserved metadata can also defeat freshness assumptions.

Before relying on a hit, check the task, scanner configuration and relevant
sources. Recompute when those assumptions change. Record whether the result was
reused or rescanned, the observed evidence and any uncertainty; a hit does not
prove correctness or a fixed percentage of token savings.

`FormCache` in `form_cache.py` is separate, process-local storage. Its similarity
uses lowercase word sets and a threshold, without expiry or project binding.
Word order is lost: a similar prompt is not evidence of equivalent intent,
arguments or authorization. Validate equivalence before reusing a response.

## Retry and plausible reuse

Inspect the stored entry and any completed callback work before retrying a miss.
Replacing one file is atomic; the lookup/scan/write sequence is not a transaction
or a lock against concurrent writers. Deleted or overwritten results require
a prior copy or a new authorized scan to recover; emitted events may remain.

Reuse across agents is a candidate when project, inputs and scanner configuration
match. Test invalidation in the target workflow and keep any callback within its
existing task scope. See the [common contract](../../docs/capability-effects.md).
