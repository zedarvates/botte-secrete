"""Security Scanner — credential leak detection (scanner) + malicious-pattern
scan (malicious, the historical API used by checkup)."""
from skills.security_scanner.scanner import scan, scan_file, scan_directory
from skills.security_scanner.malicious import scan_dir
from skills.security_scanner.malicious import scan_file as scan_file_malicious
from skills.security_scanner.report import Finding, Severity, ScanReport, scan_report

__all__ = [
    "scan", "scan_file", "scan_directory",
    "scan_dir", "scan_file_malicious", "scan_report",
    "Finding", "Severity", "ScanReport",
]
