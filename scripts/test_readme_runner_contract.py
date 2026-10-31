"""Bounded README command execution, timeout reporting and failure retention."""

import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("test_readme_commands.py")
spec = importlib.util.spec_from_file_location("readme_smoke_contract", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class ReadmeRunnerContracts(unittest.TestCase):
    def invoke(self, commands, runner):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = f"version-{smoke.__version__}-\n```bash\n" + "\n".join(commands) + "\n```\n"
            for name in ("README.md", "README.fr.md"):
                (root / name).write_text(readme, encoding="utf-8")
            (root / "pyproject.toml").write_text(
                f'version = "{smoke.__version__}"\n', encoding="utf-8")
            output = io.StringIO()
            with (patch.object(smoke, "REPO", root),
                  patch.object(smoke.subprocess, "run", side_effect=runner),
                  redirect_stdout(output)):
                code = smoke.main()
            return code, output.getvalue()

    def test_checkup_can_finish_beyond_the_ordinary_smoke_deadline(self):
        # Before the fix this same simulated completion exceeded the global
        # thirty-second deadline and main returned failure, like the CI witness.
        def completes_between_deadlines(argv, **kwargs):
            self.assertFalse(kwargs["shell"])
            if kwargs["timeout"] < 90:
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            self.assertLessEqual(kwargs["timeout"], 120)
            return subprocess.CompletedProcess(argv, 0)

        code, output = self.invoke(["python -m skills.checkup.cli ."], completes_between_deadlines)
        self.assertEqual(code, 0, output)
        self.assertIn("2 passed, 0 failed", output)

    def test_botte_entrypoint_uses_the_same_bounded_checkup_allowance(self):
        self.assertEqual(smoke.command_timeout(["botte", "checkup", "."]), 120)
        self.assertEqual(smoke.command_timeout(["botte.exe", "checkup", "."]), 120)
        self.assertEqual(smoke.command_timeout(["python", "-m", "skills.checkup.cli", "."]), 120)
        self.assertEqual(smoke.command_timeout(["botte", "--help"]), 30)
        self.assertEqual(smoke.command_timeout(["python", "-m", "skills.checkup.cli_extra", "."]), 30)

    def test_expired_deadline_stays_failed_even_when_the_next_command_passes(self):
        calls = []

        def timeout_then_pass(argv, **kwargs):
            calls.append(argv)
            if len(calls) == 1:
                self.assertEqual(kwargs["timeout"], 120)
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            self.assertEqual(kwargs["timeout"], 30)
            return subprocess.CompletedProcess(argv, 0)

        code, output = self.invoke(
            ["python -m skills.checkup.cli .", "python -m skills.cli --help"], timeout_then_pass)
        self.assertEqual(code, 1, output)
        self.assertEqual(len(calls), 2)
        self.assertIn("TIMEOUT after 120s", output)
        self.assertIn("2 passed, 1 failed", output)

    def test_nonzero_result_and_launch_error_remain_failures(self):
        for runner, expected in (
            (lambda argv, **kwargs: subprocess.CompletedProcess(argv, 7), "FAIL"),
            (lambda argv, **kwargs: (_ for _ in ()).throw(FileNotFoundError()), "ERR (FileNotFoundError)"),
        ):
            with self.subTest(expected=expected):
                code, output = self.invoke(["python -m skills.cli --help"], runner)
                self.assertEqual(code, 1, output)
                self.assertIn(expected, output)
                self.assertIn("1 passed, 1 failed", output)


def main():
    result = unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ReadmeRunnerContracts))
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"{result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
