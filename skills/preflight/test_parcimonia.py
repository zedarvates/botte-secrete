"""Run Parcimonia's behavioral and MCP contracts in the canonical CI runner."""

import unittest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        "skills.preflight.test_assessment",
        "skills.preflight.test_evaluation",
        "skills.preflight.test_github_plan",
        "skills.preflight.test_github_evidence",
        "skills.preflight.test_portable_guidance",
        "skills.llm_mcp.test_assessment_tools",
        "skills.conductor.test_preferences",
        "skills.conductor.test_selection",
        "skills.conductor.test_handoff",
        "skills.conductor.test_recipes",
        "skills.conductor.test_uncertainty",
        "skills.conductor.test_measurement",
        "skills.conductor.test_replanning",
        "skills.conductor.test_synergies",
        "skills.llm_mcp.test_plan_preferences",
        "skills.llm_mcp.test_plan_selection",
        "skills.llm_mcp.test_plan_recipes",
        "skills.llm_mcp.test_plan_uncertainty",
        "skills.llm_mcp.test_plan_replanning",
        "skills.llm_mcp.test_plan_synergies",
        "scripts.test_plan_validation_pilot",
        "scripts.test_plan_replanning_pilot",
        "scripts.test_plan_synergy_pilot",
    ])
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
