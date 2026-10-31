"""Run the integrated advisory contracts with canonical counted output.

The archived experiment is reproduced separately on its immutable source SHA.
No native model or external service is required by this test entry point.
"""
import os
from pathlib import Path


def main():
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest

    class Counts:
        passed = failed = skipped = 0

        def pytest_runtest_logreport(self, report):
            if report.failed:
                self.failed += 1
            elif report.when == "call" and report.passed:
                self.passed += 1
            elif report.skipped:
                self.skipped += 1

        def pytest_collectreport(self, report):
            if report.failed:
                self.failed += 1

    counts = Counts()
    root = Path(__file__).resolve().parents[2]
    modules = ("test_tool_router", "test_needle2", "test_needle2_study",
               "test_needle2_evidence", "test_needle2_diagnostics", "test_argument_spans")
    code = pytest.main(["--rootdir=" + str(root), "-q"] +
                       [str(root / "skills/tool_router" / (name + ".py")) for name in modules],
                       plugins=[counts])
    failed = max(counts.failed, int(code != 0 or counts.passed == 0))
    print(f"RESULT: {counts.passed} passed, {failed} failed, {counts.skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
