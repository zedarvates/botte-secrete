"""Run Parcimonia's behavioral and MCP contracts in the canonical CI runner."""

import unittest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        "skills.preflight.test_assessment",
        "skills.preflight.test_github_plan",
        "skills.preflight.test_github_evidence",
        "skills.llm_mcp.test_assessment_tools",
    ])
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
