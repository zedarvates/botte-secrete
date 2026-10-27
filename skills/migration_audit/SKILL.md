---
name: migration_audit
description: Deterministically verify that a framework, protocol, dependency, or build migration actually removed legacy paths and markers before VALIDATOR runs. Returns PASS, FAIL, or UNCERTAIN with bounded path-only evidence; never executes project code.
---

# Migration Audit

Use this stage after `BUILDER` and before `VALIDATOR`:

```text
... -> BUILDER -> MIGRATION_AUDIT -> VALIDATOR -> ...
```

Create `.botte/migration-audit.json` using
`botte.migration-audit-spec/v1`, then run:

```bash
botte migration-audit --project . --json
```

Supported checks are `text_absent`, `text_present`, `path_absent`,
`path_present`, and `paths_not_both`. Text is matched literally, not as a
regular expression. The report never contains matched source text or absolute
paths. An incomplete scan returns `UNCERTAIN`; a normal test pass cannot
override a migration-audit failure.

The stage is deterministic, stdlib-only, `SIMULATE`/`SHADOW`, and cannot grant
`ACT`, modify the audited project, or execute its code.
