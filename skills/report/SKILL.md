---
name: report
layer: GOVERN
description: Persist any audit as a timestamped Markdown and/or HTML file (name + date + time) under .botte/reports/, browsable at any time, and list saved reports. Use when the user wants audits saved to consultable files, a history of audits, or to export a checkup/metrics/infra report as .md or .html.
---

# report — audits saved as timestamped, consultable files

Audits print to the console; this keeps them. Any report dict → a self-contained
`<name>_<YYYY-MM-DD_HHMMSS>.md` and/or `.html` under `.botte/reports/`.
When a filename is already occupied, saving appends `-1`, `-2`, etc. before
the extension and creates the new file exclusively, preserving the prior file.

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
ASCII `diagram` fields as code blocks. `.botte/` is gitignored in this repository;
that does not prevent another process from copying or publishing reports.
Exposed via [[llm_mcp]] as `list_reports`. Related:
[[checkup]], [[metrics]], [[infra_advisor]], [[app_test]] (its own HTML report).

## Consequences, verification and reuse

Read [effects.json](effects.json). `save` creates the output directory and writes
one or two UTF-8 files. Invalid `fmt` values fail before creating the directory.
The renderers and `list_reports` do not persist reports or execute audit commands.
Listing returns filename metadata, not parsed findings or proof of completeness.

Rendering abbreviates list and table values; saved Markdown/HTML is not a lossless
evidence format. Keep full source JSON through the owning workflow when exact
details matter. HTML escapes values; Markdown is presentation text and can retain
links or other supplied markup. Neither renderer redacts private input.

Exclusive creation prevents timestamp collisions from overwriting a previous
file, including concurrent saves. A `both` save is still two independent writes:
suffixes can differ, and a later failure can leave a completed or partial file.
Readers may observe a file while it is being written. Inspect actual outputs after
failure before retrying; a retry produces additional files and consumes storage.

Report existence, a recent filename or successful rendering does not establish
that the source audit is current, complete or correct. Validate those facts in the
source workflow. Reuse for another audit needs target-specific retention, output
scope and a complete-data reference where required; see the
[common contract](../../docs/capability-effects.md).
