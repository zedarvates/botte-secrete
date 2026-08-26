# Migration audit gate

Normal tests can stay green while a migration still routes through a legacy
compatibility layer. `MIGRATION_AUDIT` is therefore a deterministic stage
between `BUILDER` and `VALIDATOR`; a validator cannot convert its `FAIL` or
`UNCERTAIN` result into a pass.

Create `.botte/migration-audit.json` following the
[`botte.migration-audit-spec/v1` schema](schemas/migration-audit-spec.schema.json):

```json
{
  "schema": "botte.migration-audit-spec/v1",
  "migration_id": "protocol:v1-to-v2",
  "checks": [
    {"id": "old-api-gone", "kind": "text_absent", "pattern": "LegacyClient", "include": ["**/*.py"]},
    {"id": "new-api-wired", "kind": "text_present", "pattern": "ProtocolV2", "include": ["**/*.py"]},
    {"id": "old-config-gone", "kind": "path_absent", "path": "legacy.ini"},
    {"id": "new-config-present", "kind": "path_present", "path": "protocol-v2.toml"},
    {"id": "no-dual-path", "kind": "paths_not_both", "paths": ["src/v1", "src/v2"]}
  ]
}
```

Run it without executing project code:

```bash
botte migration-audit --project . --json
```

Exit `0` means `PASS`, `1` means `FAIL`, and `2` means `UNCERTAIN` or an
invalid/unavailable specification. The machine-readable result uses
`botte.migration-audit/v1`. Evidence contains bounded relative paths and reason
codes, never matched source, literal patterns, or absolute paths.

The stage remains `SIMULATE`/`SHADOW`. It neither edits the project nor grants
`ACT` authority. Local models may help draft a spec, but the spec must be
reviewed and the audit itself remains deterministic.
