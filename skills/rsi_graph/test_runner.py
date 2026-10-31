"""Run the RSI pytest-style fixtures with the Python standard library."""

import importlib
import inspect
from pathlib import Path
import sys
import tempfile


def main():
    passed = failed = 0
    for name in ("skills.rsi_graph.test_observer", "skills.rsi_graph.test_cli"):
        module = importlib.import_module(name)
        for label, function in sorted(vars(module).items()):
            if not label.startswith("test_") or not inspect.isfunction(function):
                continue
            try:
                parameters = list(inspect.signature(function).parameters)
                if not parameters:
                    function()
                elif parameters == ["tmp_path"]:
                    with tempfile.TemporaryDirectory(prefix="botte-rsi-test-") as temporary:
                        function(Path(temporary))
                else:
                    raise ValueError("unsupported fixture: " + label)
            except Exception as error:
                failed += 1
                print("[FAIL] " + label + ": " + type(error).__name__)
            else:
                passed += 1
                print("[PASS] " + label)
    if passed + failed == 0:
        failed = 1
        print("[FAIL] no RSI tests discovered")
    print(f"RESULT: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
