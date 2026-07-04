# Bench PR comment — CI integration

When a PR is opened, run `bench` and post the delta as a comment:

```yaml
# .github/workflows/bench-pr.yml
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  bench:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install numpy
      - name: Run bench
        id: bench
        run: |
          PYTHONPATH=. python -c "
          from skills.context_profiler import profile_host
          r = profile_host('.')
          print(f'SAVINGS={r[\"reducible_tokens\"]}')
          " >> $GITHUB_OUTPUT
      - name: Comment PR
        uses: actions/github-script@v7
        with:
          script: |
            const savings = '${{ steps.bench.outputs.SAVINGS }}';
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `🧦 Botte bench: ${savings} tok reducible`
            });
```

Requires: `GITHUB_TOKEN` (auto-provided by Actions).
