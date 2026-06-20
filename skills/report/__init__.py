"""report — persist any audit as a timestamped .md/.html file, browsable any time.

    from skills.report import save, list_reports
    save("checkup", checkup_dict, fmt="both", out_dir=project/".botte"/"reports")
"""

from skills.report.report import save, list_reports, to_markdown, to_html, timestamped_name

__all__ = ["save", "list_reports", "to_markdown", "to_html", "timestamped_name"]
