---
name: completion_proof
description: Local report-only detector for completion claims without evidence markers (A11). Does not authenticate evidence or block builds.
---

# Completion proof markers (A11)

Detects reports claiming completion without an associated evidence marker:
`test_id`, `cmd_output_ref`, `artifact_hash`, a passed validation with a
reference, or supported lexical markers in text reports.

```bash
python -m skills.completion_proof.cli path/to/report.json --json
python -m skills.completion_proof.test_completion_proof
```

This is a **report-only heuristic**. A non-empty reference may point to a
nonexistent file; lexical markers can also suppress a finding. The CLI returns
zero even when findings exist. Consumers must inspect `errors` and `findings`.
No test execution, hash verification, or ingestion enforcement is performed.

The five finding fields describe evidence, estimated cost, expected benefit,
risk, and a minimal suggested remedy. These are qualitative, not measurements.

See the [replayable demonstration](../../docs/demos/completion-proof/README.md)
and its negative control before treating a clean report as verified success.
