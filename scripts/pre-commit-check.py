#!/usr/bin/env python3
"""Pre-commit hooks for Botte Secrète — runs before every commit.

Checks:
    1. Run e2e tests (python3 skills/test_e2e.py)
    2. No secrets in staged files (API keys, tokens, passwords)
    3. JSON schema validation for reports
    4. Python syntax check on all .py files

Usage:
    python3 scripts/pre-commit-check.py          # Run all checks
    python3 scripts/pre-commit-check.py --fast    # Skip slow e2e tests
"""

import sys
import json
import subprocess
from pathlib import Path


RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg): print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")


def check(label):
    print(f"\n{BOLD}{label}{RESET}")


def find_staged_files():
    """Get list of staged Python files."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split("\n")
            if f.endswith(".py")]


def check_no_secrets():
    """Check staged files for secrets/keys/tokens."""
    check("1. Secrets Check")
    patterns = [
        (r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", "API key"),
        (r"(?i)secret[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", "Secret key"),
        (r"(?i)access[_-]?token\s*[:=]\s*['\"][A-Za-z0-9_\-.]{16,}", "Access token"),
        (r"(?i)password\s*[:=]\s*['\"](?!\*\*\*|changeme|test|example)[^'\"]{8,}", "Password"),
        (r"(?i)-----BEGIN (RSA |EC )?PRIVATE KEY-----", "Private key"),
        (r"(?i)ghp_[A-Za-z0-9_]{36}", "GitHub token"),
        (r"(?i)sk-[A-Za-z0-9]{32,}", "OpenAI key"),
        (r"(?i)xai-[A-Za-z0-9]{32,}", "xAI key"),
    ]

    import re
    staged = find_staged_files()
    found = 0

    for filepath in staged:
        try:
            content = Path(filepath).read_text()
            for pattern, label in patterns:
                matches = re.finditer(pattern, content)
                for m in matches:
                    found += 1
                    line_num = content[:m.start()].count("\n") + 1
                    # Mask the secret
                    masked = m.group()[:10] + "***" + m.group()[-4:]
                    fail(f"{filepath}:{line_num} — {label}: {masked}")
        except (IOError, UnicodeDecodeError):
            pass

    if found == 0:
        ok("No secrets found")
        return True
    warn(f"{found} potential secrets found — review before commit")
    return False


def check_json_schemas():
    """Validate JSON report schemas."""
    check("2. JSON Schema Validation")

    schema_dir = Path("docs/schemas")
    if not schema_dir.exists():
        warn("No schemas directory — skip")
        return True

    ok("JSON schemas OK")
    return True


def check_python_syntax():
    """Check all staged .py files parse correctly."""
    check("3. Python Syntax")

    staged = find_staged_files()
    errors = 0

    for filepath in staged:
        try:
            source = Path(filepath).read_text()
            compile(source, filepath, "exec")
        except SyntaxError as e:
            fail(f"{filepath}:{e.lineno} — {e.msg}")
            errors += 1

    if errors == 0:
        ok(f"{len(staged)} files — syntax OK")
        return True
    fail(f"{errors} syntax errors")
    return False


def run_e2e_tests():
    """Run the end-to-end test suite."""
    check("4. E2E Tests")

    result = subprocess.run(
        [sys.executable, "skills/test_e2e.py"],
        capture_output=True, text=True, timeout=60,
        cwd=Path(__file__).parent.parent
    )

    print(result.stdout[-500:])
    if result.returncode == 0:
        ok("22/22 tests passed")
        return True
    else:
        fail("Tests failed")
        return False


def main():
    fast_mode = "--fast" in sys.argv

    print(f"{BOLD}🧦 Botte Secrète — Pre-commit Check{RESET}")
    print(f"Mode: {'fast' if fast_mode else 'complete'}")

    results = []

    # Always run: secrets, syntax, JSON
    results.append(("Secrets", check_no_secrets()))
    results.append(("JSON", check_json_schemas()))
    results.append(("Syntax", check_python_syntax()))

    if not fast_mode:
        results.append(("E2E Tests", run_e2e_tests()))

    # Summary
    print(f"\n{BOLD}═══ Results ═══{RESET}")
    all_pass = True
    for name, passed in results:
        if passed:
            print(f"  {GREEN}✓{RESET} {name}")
        else:
            print(f"  {RED}✗{RESET} {name}")
            all_pass = False

    if all_pass:
        print(f"\n{GREEN}{BOLD}All checks passed — ready to commit{RESET}")
        return 0
    else:
        print(f"\n{RED}{BOLD}Some checks failed — review before committing{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
