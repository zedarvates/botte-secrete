---
name: test-readme
description: Verify every command cited in README.md actually runs
version: 1.0.0
---

# README Command Test

```bash
python scripts/test_readme_commands.py
```

Non-zero exit if any command fails. Skips git push, pip install, cargo, curl.
