---
name: "Parallel test runner"
about: "Run test suites in parallel for faster CI"
---

# Parallel test runner for CI

The `scripts/run_tests.py` script runs suites sequentially. For CI with
multiple cores, split into parallel jobs:

```yaml
# In .github/workflows/ci.yml
jobs:
  test-parallel:
    strategy:
      matrix:
        suite: [e2e, checkup, auto_router, security_scanner, nn_audit,
                context_profiler, local_harness, botte_nn, fallow_scanner]
    steps:
      - run: PYTHONPATH=. python -m skills.${{ matrix.suite }}.test_${{ matrix.suite }}
```
