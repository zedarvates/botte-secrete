# SKILL.md dedup — docs_steward recommendation

When multiple SKILL.md files repeat the same boilerplate phrases, extract common
fragments into `_shared/` and include by reference:

```markdown
<!-- include: _shared/footer.md -->
```

## Common boilerplate detected

| Phrase | Files | Savings (/5 skills loaded) |
|--------|-------|---------------------------|
| "pure stdlib" | 15 skills | ~75 tok |
| "0 cloud tokens" | 22 skills | ~88 tok |
| "Related:" table | 8 skills | ~200 tok |

## Recommendation

Create `skills/_shared/footer.md` with the common footer and reference it in
SKILL.md files. The context_budget skill already supports loading only
referenced fragments, reducing always-on cost by ~300 tok when 5+ skills are loaded.
