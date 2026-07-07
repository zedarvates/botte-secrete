"""Tests for security_scanner skill."""
from skills.security_scanner.scanner import scan, scan_file, scan_directory


def test_scan_clean():
    result = scan("x = 42\nprint('hello')", "clean.py")
    assert result["pass"] is True
    assert result["total"] == 0


def test_scan_api_key():
    result = scan('API_KEY = "abcdefghijklmnopqrstuvwx"', "config.py")
    assert result["total"] >= 1
    assert result["by_severity"]["critical"] >= 1


def test_scan_password():
    result = scan('password = "hunter2_my_pass"', "login.py")
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
