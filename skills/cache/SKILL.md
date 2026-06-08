# Project Cache
Avoids re-scanning between agents. First agent scans, subsequent agents read cache.

**Trigger:** When multiple agents work on the same project sequentially.

**Usage:**
```python
from skills.cache import ProjectCache
cache = ProjectCache(project_root)
scan = cache.get_or_scan(lambda: scanner.scan())
cache.set_audit_report(report)
```

**Module:** `skills/cache`
**Storage:** `.botte-cache/` directory
**TTL:** 24 hours
**Savings:** -50% re-scan tokens
