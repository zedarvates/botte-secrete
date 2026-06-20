---
name: report
layer: GOVERN
description: Persist any audit as a timestamped Markdown and/or HTML file (name + date + time) under .botte/reports/, browsable at any time, and list saved reports. Use when the user wants audits saved to consultable files, a history of audits, or to export a checkup/metrics/infra report as .md or .html.
---

# report — audits saved as timestamped, consultable files

Audits print to the console; this keeps them. Any report dict → a self-contained
`<name>_<YYYY-MM-DD_HHMMSS>.md` and/or `.html` under `.botte/reports/`.

## Save an audit

The audit CLIs take `--save [md|html|both]`:

```bash
python -m skills.checkup.cli .        --save both   # checkup_2026-06-20_142838.md/.html
python -m skills.metrics.cli .        --save html
python -m skills.infra_advisor.cli auto . --save md
```

## Browse them any time

```bash
python -m skills.report.cli list                # most recent first
python -m skills.report.cli list --json
```

## Programmatic

```python
from skills.report import save, list_reports
save("audit", report_dict, fmt="both", out_dir=project/".botte"/"reports")
list_reports(project/".botte"/"reports")
```

The renderer handles scalars, lists, list-of-dicts → tables, nested dicts, and
ASCII `diagram` fields as code blocks. `.botte/` is gitignored, so reports stay
local per machine/project. Exposed via [[llm_mcp]] as `list_reports`. Related:
[[checkup]], [[metrics]], [[infra_advisor]], [[app_test]] (its own HTML report).
