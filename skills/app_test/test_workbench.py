"""Canonical aggregate: skipped adapter qualifications never count as passes."""
import unittest


MODULES = (
    "skills.app_test.test_reducer", "skills.app_test.test_flaky",
    "skills.app_test.test_mutation", "skills.app_test.test_explorer",
    "skills.app_test.test_prioritization", "skills.app_test.test_process_oracle",
    "skills.app_test.test_workbench_cli", "skills.preflight.test_conformance",
    "skills.app_test.test_memory_bridge", "skills.app_test.test_knowledge_links",
    "skills.app_test.test_memory_cli",
    "skills.app_test.test_memory_retrieval", "skills.app_test.test_recall_cli",
    "skills.app_test.test_recalled_links",
)


def main():
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in MODULES)
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    passed = result.testsRun - failed - skipped
    print(f"{passed} passed, {failed} failed, {skipped} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
