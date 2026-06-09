# Code Fingerprinting (P13)
Hash every function/method, only re-analyze changed code.

**Trigger:** Before every audit — check fingerprints, skip unchanged files.

**Token savings:** -80% on re-analysis of stable codebases

**Usage:**
```python
from skills.code_fingerprint import CodeFingerprinter, skip_if_unchanged
fp = CodeFingerprinter()
result = skip_if_unchanged(fp, project_path, analyze_fn)
# If nothing changed: {"skipped": True, "reason": "no changes detected"}
```

**Module:** `skills/code_fingerprint`
**Cache:** .botte-cache/fingerprints.json
