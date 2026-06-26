"""security_scanner — scan Python code for malicious patterns.

    from skills.security_scanner import scan_file, scan_dir, scan_report
    from skills.security_scanner import Finding, Severity

    results = scan_dir("skills/", fail_on="critical")
    report = scan_report(results)
    print(report.compact())
"""

from skills.security_scanner.scanner import scan_file, scan_dir
from skills.security_scanner.report import Finding, Severity, ScanReport, scan_report

__all__ = [
    "scan_file", "scan_dir", "scan_report",
    "Finding", "Severity", "ScanReport",
]
