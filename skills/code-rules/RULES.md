# Code Rules — Token-Efficient Coding Standards

> *"The best optimization is subtraction."*

## The 3 Taxes (before adding ANY dependency)

1. **Latency tax**: How many ms/µs does it cost per call?
2. **Security surface tax**: How many transitive vulnerabilities do you import?
3. **Cold start tax**: How many seconds to load the module on first call?

## Core Rules

### 1. stdlib First
- `http.server` before FastAPI for micro-APIs
- `sqlite3` (WAL mode) before PostgreSQL for < 100k rows
- `pathlib`, `dataclasses(slots=True)`, `functools.lru_cache` are your best friends
- No dependency that provides less than 20 lines of real utility

### 2. Flat Architecture
- No service/repository/mapper layers if one function suffices
- Route → Handler → DB. No abstraction circles
- One function = one responsibility, not one class

### 3. Data-Oriented Design
- Batch processing: column-oriented (SoA), not row-oriented (AoS)
- Cache misses cost 100-300 CPU cycles. Keep hot data contiguous

### 4. Database Choice
| Scale | Solution | Cost |
|-------|----------|------|
| < 10k rows | SQLite WAL | 0€ |
| < 10M vectors | pgvector | ~50€/mo |
| < 100M vectors | Qdrant | 0€ (self-hosted) |
| > 100M | Milvus | ~200€/mo |

### 5. Module Registration Pattern
To extend an `http.server` without touching the core, each module exposes `register(db_path)`.

### 6. File Size Hard Limit
**No single source file should exceed 2000 lines. Target: 1500 lines max.**
Split by responsibility, not arbitrarily.

### 7. Verification Before Announcement
NEVER announce a result without verifying it yourself.
- Server UP? `curl /health` AND capture actual response
- File created? `ls -la` + read first lines
- Service configured? Process running AND responding on port
- "Should work" is NOT verification

### 8. Never Deliver Half-Finished Work
If a task has 5 sub-steps, test EACH step before moving to the next.
If blocked on a step, DECLARE it explicitly rather than moving on.

### 9. User Sovereignty Over Data
- NEVER invent quantities, prices, or numerical data
- "I don't know" is better than a fabricated answer
- Never ask users to repeat sensitive tokens (PAT, API keys)

### 10. READMEs in English
All project READMEs and public-facing documentation MUST be English-only.
French is acceptable for internal comments and private notes.
