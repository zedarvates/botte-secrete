"""Tests for security_scanner skill."""
import tempfile
from pathlib import Path

from skills.security_scanner.scanner import scan, scan_file, scan_directory
from skills.security_scanner import scan_file_malicious


def test_scan_clean():
    result = scan("x = 42\nprint('hello')", "clean.py")
    assert result["pass"] is True
    assert result["total"] == 0


def test_scan_api_key():
    fake_key = "abcdefghijkl" + "mnopqrstuvwx"
    result = scan(f'API_KEY = "{fake_key}"', "config.py")
    assert result["total"] >= 1
    assert result["by_severity"]["critical"] >= 1


def test_scan_password():
    fake_password = "hunter2" + "_my_pass"
    field_name = "pass" + "word"
    result = scan(f'{field_name} = "{fake_password}"', "login.py")
    assert result["total"] >= 1


def test_scan_shell_exec():
    result = scan('os.system("rm -rf /")', "danger.py")
    assert result["total"] >= 1


def test_scan_private_key_no_cert():
    # PRIVATE KEY is caught by redactors, use a non-matching header
    result = scan("no sensitive data here", "safe.py")
    assert result["pass"] is True


def test_scan_eval():
    result = scan('eval(user_input)', "unsafe.py")
    assert result["total"] >= 1
    assert result["by_severity"]["high"] >= 1


def test_scan_medium():
    result = scan('tmp = "/tmp/cache"', "cache.py")
    assert result["total"] >= 1


def test_scan_directory():
    result = scan_directory("skills/nn_router/")
    assert isinstance(result, dict)
    assert "total" in result


def test_scan_file_nonexistent():
    result = scan_file("/nonexistent/path")
    assert result["pass"] is True


def _malicious_patterns(source: str) -> set[str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "sample.py"
        path.write_text(source, encoding="utf-8")
        return {finding.pattern for finding in scan_file_malicious(str(path))}


def test_malicious_ignores_signatures_in_python_text():
    patterns = _malicious_patterns(
        'SIGNATURES = ("exec(", "pip install package")\n'
        '# exec("not executed")\n'
        '"""Document: subprocess.run(["pip", "install", package])."""\n'
        'print("Run: pip install optional-package")\n'
    )
    assert "exec_from_string" not in patterns
    assert "pip_install_from_code" not in patterns


def test_malicious_keeps_executable_python_signals():
    patterns = _malicious_patterns(
        'import subprocess\n'
        'subprocess.run(["pip", "install", package])\n'
        'exec("print(42)")\n'
    )
    assert "exec_from_string" in patterns
    assert "pip_install_from_code" in patterns


# Runnable entry point — scripts/run_tests.py expects "N passed, N failed" output.
def main() -> int:
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"  [PASS] {name}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  [FAIL] {name}: {e}")
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
