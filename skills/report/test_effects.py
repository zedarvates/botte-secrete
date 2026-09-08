"""Report saving must preserve earlier evidence when timestamps collide."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from skills.report import save, list_reports

report_module = import_module("skills.report.report")


class ReportEffectsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(report_module, "timestamped_name",
                     side_effect=lambda name, ext: f"{name}_2026-09-08_120000.{ext}").start()

    def test_concurrent_saves_keep_each_result_and_existing_bytes(self):
        first = save("audit", {"value": "original"}, out_dir=self.root)
        originals = {p: Path(p).read_bytes() for p in first}
        def persist(i):
            return save("audit", {"value": f"marker-{i}"}, out_dir=self.root)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(persist, range(12)))
        paths = first + [path for pair in results for path in pair]
        self.assertEqual(len(set(paths)), 26)
        for p, content in originals.items():
            self.assertEqual(Path(p).read_bytes(), content)
        for i, pair in enumerate(results):
            for path in pair:
                self.assertIn(f"marker-{i}", Path(path).read_text(encoding="utf-8"))
        self.assertEqual(len(list_reports(self.root)), 26)

    def test_collision_suffixes_keep_report_name_and_numeric_order(self):
        paths = [save("audit", {"value": i}, fmt="md", out_dir=self.root)[0]
                 for i in range(12)]
        rows = list_reports(self.root)
        self.assertEqual([r["path"] for r in rows], paths[::-1])
        self.assertTrue(all(r["name"] == "audit" and r["when"] == "2026-09-08_120000"
                            and set(r) == {"name", "when", "fmt", "path"} for r in rows))

    def test_invalid_format_fails_before_creating_output_directory(self):
        target = self.root / "absent"
        with self.assertRaises(ValueError):
            save("audit", {}, fmt="pdf", out_dir=target)
        self.assertFalse(target.exists())


def main():
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(ReportEffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
