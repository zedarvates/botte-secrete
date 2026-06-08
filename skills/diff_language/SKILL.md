# Diff Language
Compact agent-native diff format for token-efficient code change descriptions.

**Trigger:** When generating diffs, fix reports, or audit findings.

**Format:** `!!+f:file.py:42:symbol:detail`
- Severity: !! (crit), ! (err), ~ (warn), . (info)
- Ops: +f (fix), -f (skip), +d (dead), +s (secret), +p (dup), +c (complex)

**Module:** `skills/diff_language`

**Savings:** 47-55% vs verbose markdown
**Roundtrip:** lossless parse + serialize
