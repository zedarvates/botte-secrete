"""Regression tests for the packaged ``botte`` command router."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from skills import cli


def main() -> int:
    state = [0, 0]

    def check(label: str, condition: bool) -> None:
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        state[0 if condition else 1] += 1

    captured: list[list[str]] = []

    def fake_main(argv):
        captured.append(argv)
        return 0

    module = SimpleNamespace(main=fake_main)
    with patch("importlib.import_module", return_value=module):
        check("gain routes to project metrics", cli.main(["gain", "."]) == 0)
        check("gain preserves the project argument", captured[-1] == ["."])
        check("discover routes to infrastructure audit",
              cli.main(["discover", ".", "--json"]) == 0)
        check("discover inserts the safe auto subcommand",
              captured[-1] == ["auto", ".", "--json"])
        check("discover keeps an explicit tips subcommand",
              cli.main(["discover", "tips", "--json"]) == 0
              and captured[-1] == ["tips", "--json"])
        check("qa routes to the quality compass",
              cli.main(["qa", "summarize logs", "--json"]) == 0)
        check("qa preserves the intuitive bare-task shortcut",
              captured[-1] == ["summarize logs", "--json"])
        check("asset-qa routes to family-isolated quality memory",
              cli.main(["asset-qa", "status", ".", "--json"]) == 0
              and captured[-1] == ["status", ".", "--json"])
        check("migration-audit routes to deterministic gate",
              cli.main(["migration-audit", "spec.json", "--json"]) == 0
              and captured[-1] == ["spec.json", "--json"])
        check("contract routes to typed contract validation",
              cli.main(["contract", "validate", "mission.json"]) == 0
              and captured[-1] == ["validate", "mission.json"])
        check("run preserves the bounded mission arguments",
              cli.main(["run", "mission.json", "--plan", "audit"]) == 0
              and captured[-1] == ["mission.json", "--plan", "audit"])
        check("lease routes to recoverable workspace management",
              cli.main(["lease", "--project", ".", "list"]) == 0
              and captured[-1] == ["--project", ".", "list"])
        check("review routes to independent Gauntlet replay",
              cli.main(["review", "mission.json", "handoff.json"]) == 0
              and captured[-1] == ["mission.json", "handoff.json"])
        check("rules routes to deterministic semantic drift audit",
              cli.main(["rules", "audit", ".", "--json"]) == 0
              and captured[-1] == ["audit", ".", "--json"])

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
