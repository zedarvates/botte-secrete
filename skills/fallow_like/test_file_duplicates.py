"""Independent behavioral checks for bounded exact-file duplicate discovery."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from skills.fallow_like import file_duplicates as module
from skills.fallow_like.file_duplicates import find_file_duplicates


class FileDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, path, data=b"same"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def scan(self, **kwargs):
        return find_file_duplicates(str(self.root), **kwargs)

    def test_exact_copies_are_confirmed_and_unique_files_are_not_listed(self):
        self.write("a", b"copy")
        self.write("nested/b", b"copy")
        self.write("different", b"else")
        self.write("unique_size", b"other-size")
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["groups"][0]["paths"], ["a", "nested/b"])
        self.assertEqual(result["groups"][0]["match"], "exact_bytes")
        self.assertEqual(result["summary"]["logical_duplicate_bytes"], 4)
        self.assertNotIn("unique_size", json.dumps(result["groups"]))
        self.assertFalse(result["atomic_snapshot"])

    def test_same_size_different_bytes_are_not_duplicates(self):
        self.write("a", b"first")
        self.write("b", b"other")
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["group_count"], 0)
        self.assertEqual(result["summary"]["bytes_read"], 10)

    def test_executable_extension_copies_have_matching_file_types(self):
        self.write("program.exe", b"same-content")
        self.write("script.cmd", b"same-content")
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["groups"][0]["paths"], ["program.exe", "script.cmd"])

    def test_forced_hash_collision_still_requires_bytes_equal(self):
        self.write("a", b"alpha")
        self.write("b", b"bravo")
        self.write("c", b"alpha")

        class Collision:
            def update(self, _data):
                pass

            def hexdigest(self):
                return "0" * 64

        with patch.object(module.hashlib, "sha256", Collision):
            result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["groups"][0]["paths"], ["a", "c"])
        self.assertGreater(result["summary"]["comparison_bytes_read"], 0)

    @unittest.skipUnless(hasattr(os, "link"), "hardlinks unavailable")
    def test_hardlinks_are_separate_and_do_not_inflate_logical_copies(self):
        original = self.write("a", b"content")
        try:
            os.link(original, self.root / "alias")
        except OSError as error:
            self.skipTest(str(error))
        self.write("copy", b"content")
        result = self.scan()
        self.assertEqual(result["hardlink_group_count"], 1)
        self.assertEqual(result["hardlink_groups"][0]["paths"], ["a", "alias"])
        self.assertEqual(result["groups"][0]["file_count"], 2)
        self.assertEqual(result["summary"]["logical_duplicate_bytes"], 7)

    @unittest.skipUnless(hasattr(os, "link"), "hardlinks unavailable")
    def test_hardlink_alias_extensions_do_not_create_false_permission_changes(self):
        original = self.write("program.exe", b"same-content")
        try:
            os.link(original, self.root / "program.txt")
        except OSError as error:
            self.skipTest(f"hardlink fixture unavailable: {error}")
        self.write("copy.bin", b"same-content")
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["hardlink_group_count"], 1)
        self.assertEqual(result["hardlink_groups"][0]["paths"], ["program.exe", "program.txt"])
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["groups"][0]["file_count"], 2)
        self.assertEqual(result["summary"]["logical_duplicate_bytes"], len(b"same-content"))

    def test_empty_directory_and_empty_file_copies(self):
        empty = self.scan()
        self.assertEqual(empty["status"], "complete")
        self.assertEqual(empty["summary"]["bytes_read"], 0)
        self.write("a", b"")
        self.write("b", b"")
        result = self.scan()
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["summary"]["bytes_read"], 0)
        self.assertEqual(result["groups"][0]["logical_duplicate_bytes"], 0)

    def test_hash_and_comparison_reads_share_one_budget(self):
        self.write("a", b"copy")
        self.write("b", b"copy")
        partial = self.scan(max_total_bytes=8)
        self.assertEqual(partial["status"], "partial")
        self.assertIn("max_total_bytes", partial["partial_reasons"])
        self.assertEqual(partial["group_count"], 0)
        self.assertEqual(partial["summary"]["hash_bytes_read"], 8)
        complete = self.scan(max_total_bytes=16)
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["summary"]["hash_bytes_read"], 8)
        self.assertEqual(complete["summary"]["comparison_bytes_read"], 8)
        self.assertEqual(complete["summary"]["bytes_read"], 16)

    def test_budget_is_never_exceeded_during_partial_hash(self):
        self.write("a", b"copy")
        self.write("b", b"copy")
        result = self.scan(max_total_bytes=6)
        self.assertEqual(result["status"], "partial")
        self.assertLessEqual(result["summary"]["bytes_read"], 6)
        self.assertEqual(result["group_count"], 0)

    def test_file_count_and_size_caps_produce_partial_reports(self):
        self.write("a", b"same")
        self.write("b", b"same")
        limited = self.scan(max_files=1)
        self.assertTrue(limited["scan_partial"])
        self.assertIn("max_files", limited["partial_reasons"])
        self.assertEqual(limited["summary"]["files_seen"], 1)
        oversized = self.scan(max_file_bytes=3)
        self.assertIn("max_file_bytes", oversized["partial_reasons"])
        self.assertEqual(oversized["summary"]["bytes_read"], 0)

    def test_entry_count_and_depth_caps_are_independent_of_files(self):
        self.write("a")
        self.write("b")
        self.write("child/c")
        entries = self.scan(max_entries=2)
        self.assertEqual(entries["summary"]["entries_examined"], 2)
        self.assertIn("max_entries", entries["partial_reasons"])
        depth = self.scan(max_depth=0)
        self.assertIn("max_depth", depth["partial_reasons"])
        self.assertEqual(depth["summary"]["files_seen"], 2)

    def test_default_and_explicit_exclusions_are_declared(self):
        self.write(".git/hidden")
        self.write("visible")
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertIn(".git", result["excluded_dirs"])
        self.assertEqual(result["summary"]["files_seen"], 1)
        explicit = self.scan(exclude_dirs=[])
        self.assertEqual(explicit["excluded_dirs"], [])
        self.assertEqual(explicit["summary"]["files_seen"], 2)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_targets_are_never_scanned(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, "outside").write_bytes(b"same")
        self.write("real", b"same")
        try:
            os.symlink(outside.name, self.root / "linked_dir", target_is_directory=True)
            os.symlink(self.root / "real", self.root / "linked_file")
        except OSError as error:
            self.skipTest(str(error))
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["summary"]["files_seen"], 1)
        self.assertEqual(result["group_count"], 0)
        self.assertEqual(result["skip_count"], 2)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_special_files_are_excluded_without_opening(self):
        os.mkfifo(self.root / "pipe")
        result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["summary"]["files_seen"], 0)
        self.assertEqual(result["skips"][0]["reason"], "special_file_excluded")

    def test_reparse_attributes_exclude_entries_and_reject_root(self):
        self.write("a")
        self.write("b")
        self.write("junction/private")
        original = os.lstat

        class ReparseStat:
            def __init__(self, info):
                self.info = info
                self.st_file_attributes = getattr(info, "st_file_attributes", 0) | 0x400
                self.st_reparse_tag = 0xA0000003

            def __getattr__(self, name):
                return getattr(self.info, name)

        def fake_entry(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            return ReparseStat(info) if os.fspath(path) == str(self.root / "junction") else info

        with patch.object(module.os, "supports_dir_fd", set()), patch.object(module.os, "lstat", fake_entry):
            result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["summary"]["files_seen"], 2)
        self.assertEqual(result["groups"][0]["paths"], ["a", "b"])
        self.assertIn("reparse_point_excluded", [item["reason"] for item in result["skips"]])

        def fake_root(path, *args, **kwargs):
            return ReparseStat(original(path, *args, **kwargs))

        with patch.object(module.os, "lstat", fake_root), self.assertRaises(ValueError):
            self.scan()

    def test_reparse_replacement_before_or_during_read_is_partial(self):
        self.write("a")
        self.write("b")
        original_stat = os.lstat
        original_hash = module._Scanner.hash_file
        original_read = os.read
        for phase in ("before_open", "during_read"):
            changed = False

            class ReparseStat:
                def __init__(self, info):
                    self.info = info
                    self.st_file_attributes = getattr(info, "st_file_attributes", 0) | 0x400
                    self.st_reparse_tag = 0xA0000003

                def __getattr__(self, name):
                    return getattr(self.info, name)

            def fake_entry(path, *args, **kwargs):
                info = original_stat(path, *args, **kwargs)
                return ReparseStat(info) if changed and os.fspath(path) == str(self.root / "a") else info

            def change_before_hash(scanner, record):
                nonlocal changed
                if phase == "before_open":
                    changed = True
                return original_hash(scanner, record)

            def change_during_read(descriptor, count):
                nonlocal changed
                data = original_read(descriptor, count)
                if phase == "during_read":
                    changed = True
                return data

            with self.subTest(phase=phase), patch.object(module.os, "supports_dir_fd", set()), \
                    patch.object(module.os, "lstat", fake_entry), \
                    patch.object(module._Scanner, "hash_file", change_before_hash), \
                    patch.object(module.os, "read", change_during_read):
                result = self.scan()
            self.assertTrue(changed)
            self.assertTrue(result["scan_partial"])
            self.assertEqual(result["group_count"], 0)

    @unittest.skipUnless(os.name == "nt", "Windows junction creation unavailable on this platform")
    def test_windows_junction_target_is_not_scanned(self):
        self.write("a")
        self.write("b")
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, "private").write_bytes(b"same")
        junction = self.root / "junction"
        try:
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), outside.name],
                                    capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.skipTest(f"junction fixture unavailable: {error}")
        if result.returncode != 0:
            self.skipTest(f"mklink /J unavailable: exit {result.returncode}")
        self.addCleanup(junction.rmdir)
        report = self.scan()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["summary"]["files_seen"], 2)
        self.assertIn("reparse_point_excluded", [item["reason"] for item in report["skips"]])
        with self.assertRaises(ValueError):
            find_file_duplicates(str(junction))

    def test_change_during_read_is_partial_and_not_verified(self):
        first = self.write("a", b"same")
        self.write("b", b"same")
        original_read = os.read
        changed = False

        def read_then_change(descriptor, count):
            nonlocal changed
            data = original_read(descriptor, count)
            if not changed:
                changed = True
                first.write_bytes(b"DIFF")
            return data

        with patch.object(module.os, "read", read_then_change):
            result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["group_count"], 0)
        self.assertIn("file_changed", result["partial_reasons"])

    def test_disappearing_file_during_open_is_partial(self):
        self.write("a")
        self.write("b")
        original = module._Scanner.hash_file
        removed = False

        def remove_then_hash(scanner, record):
            nonlocal removed
            if not removed:
                removed = True
                (self.root / record["path"]).unlink()
            return original(scanner, record)

        with patch.object(module._Scanner, "hash_file", remove_then_hash):
            result = self.scan()
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["group_count"], 0)
        self.assertGreater(result["error_count"], 0)

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"), "nonblocking FIFO unavailable")
    def test_regular_file_replaced_by_fifo_after_lstat_does_not_block(self):
        self.write("a")
        self.write("b")
        original = os.open
        changed = False

        def replace_before_open(path, flags, *args, **kwargs):
            nonlocal changed
            if not changed and str(path) in ("a", str(self.root / "a")):
                changed = True
                self.assertTrue(flags & os.O_NONBLOCK)
                (self.root / "a").unlink()
                os.mkfifo(self.root / "a")
            return original(path, flags, *args, **kwargs)

        with patch.object(module.os, "open", replace_before_open):
            result = self.scan()
        self.assertTrue(changed)
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["group_count"], 0)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd,
                         "anchored POSIX directory access unavailable")
    def test_parent_replaced_by_external_symlink_is_not_followed(self):
        self.write("a/x", b"same")
        self.write("b", b"same")
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, "x").write_bytes(b"private-outside")
        original = os.open
        changed = False

        def replace_parent(path, flags, *args, **kwargs):
            nonlocal changed
            if not changed and path == "a" and flags & os.O_DIRECTORY:
                changed = True
                (self.root / "a").rename(self.root / "old_a")
                os.symlink(outside.name, self.root / "a", target_is_directory=True)
            return original(path, flags, *args, **kwargs)

        # The first 'a' open belongs to traversal; swap only after inventory.
        original_hash = module._Scanner.hash_file

        def hash_with_race(scanner, record):
            with patch.object(module.os, "open", replace_parent):
                return original_hash(scanner, record)

        with patch.object(module._Scanner, "hash_file", hash_with_race):
            result = self.scan()
        self.assertTrue(changed)
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["group_count"], 0)
        self.assertEqual(result["summary"]["bytes_read"], 4)  # only internal b

    def test_final_revalidation_rejects_changed_confirmed_path(self):
        self.write("a", b"same")
        self.write("b", b"same")
        original = module._Scanner.equal_files

        def change_after_comparison(scanner, left, right):
            equal = original(scanner, left, right)
            (self.root / left["path"]).write_bytes(b"DIFF")
            return equal

        with patch.object(module._Scanner, "equal_files", change_after_comparison):
            result = self.scan()
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["group_count"], 0)
        self.assertIn("file_changed", result["partial_reasons"])

    def test_renamed_and_recreated_root_invalidates_old_anchored_groups(self):
        self.write("a", b"same")
        self.write("b", b"same")
        moved = self.root.with_name(self.root.name + "-moved")
        self.addCleanup(shutil.rmtree, moved, True)
        original = module._Scanner.equal_files
        renamed = False

        def replace_root(scanner, left, right):
            nonlocal renamed
            equal = original(scanner, left, right)
            if not renamed:
                renamed = True
                self.root.rename(moved)
                self.root.mkdir()
            return equal

        with patch.object(module._Scanner, "equal_files", replace_root):
            result = self.scan()
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["root"], str(self.root))
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["hardlink_groups"], [])
        self.assertEqual(result["summary"]["logical_duplicate_bytes"], 0)

    def test_recreated_parent_invalidates_nested_groups(self):
        self.write("nested/a", b"same")
        self.write("nested/b", b"same")
        original = module._Scanner.equal_files
        renamed = False

        def replace_parent(scanner, left, right):
            nonlocal renamed
            equal = original(scanner, left, right)
            if not renamed:
                renamed = True
                (self.root / "nested").rename(self.root / "old_nested")
                (self.root / "nested").mkdir()
            return equal

        with patch.object(module._Scanner, "equal_files", replace_parent):
            result = self.scan()
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["groups"], [])

    def test_portable_path_check_fallback_remains_explicit(self):
        self.write("a")
        self.write("b")
        with patch.object(module.os, "supports_dir_fd", set()):
            result = self.scan()
        self.assertEqual(result["filesystem_access"], "path_checks")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["group_count"], 1)

    def test_distinct_path_and_descriptor_ctime_semantics_are_stable(self):
        self.write("a")
        self.write("b")
        original = os.fstat

        class DescriptorStat:
            def __init__(self, info):
                self.info = info
                self.st_ctime_ns = info.st_ctime_ns + 1_000_000_000

            def __getattr__(self, name):
                return getattr(self.info, name)

        with patch.object(module.os, "supports_dir_fd", set()), patch.object(
                module.os, "fstat", side_effect=lambda descriptor: DescriptorStat(original(descriptor))):
            result = self.scan()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["summary"]["bytes_read"], 16)

    def test_descriptor_ctime_change_is_detected_with_unchanged_path_mtime(self):
        first = self.write("a")
        self.write("b")
        path_mtime = first.stat().st_mtime_ns
        original = os.fstat
        calls = {}

        class DescriptorStat:
            def __init__(self, info, delta):
                self.info = info
                self.st_ctime_ns = info.st_ctime_ns + delta

            def __getattr__(self, name):
                return getattr(self.info, name)

        def changed_descriptor(descriptor):
            calls[descriptor] = calls.get(descriptor, 0) + 1
            phase = (calls[descriptor] - 1) % 2
            return DescriptorStat(original(descriptor), 1_000_000_000 + phase)

        with patch.object(module.os, "supports_dir_fd", set()), patch.object(
                module.os, "fstat", side_effect=changed_descriptor):
            result = self.scan()
        self.assertTrue(result["scan_partial"])
        self.assertIn("file_changed", result["partial_reasons"])
        self.assertEqual(result["group_count"], 0)
        self.assertEqual(first.stat().st_mtime_ns, path_mtime)

    def test_final_descriptor_change_is_detected_when_path_times_stay_unchanged(self):
        first = self.write("a")
        second = self.write("b")
        before = [(path.stat().st_mtime_ns, path.stat().st_ctime_ns) for path in (first, second)]
        original_stat = os.fstat
        original_equal = module._Scanner.equal_files
        changed = False

        class DescriptorStat:
            def __init__(self, info):
                self.info = info
                self.st_ctime_ns = info.st_ctime_ns + 1_000_000_000 + int(changed)

            def __getattr__(self, name):
                return getattr(self.info, name)

        def change_after_comparison(scanner, left, right):
            nonlocal changed
            equal = original_equal(scanner, left, right)
            changed = True
            return equal

        with patch.object(module.os, "supports_dir_fd", set()), \
                patch.object(module.os, "fstat", side_effect=lambda descriptor: DescriptorStat(original_stat(descriptor))), \
                patch.object(module._Scanner, "equal_files", change_after_comparison):
            result = self.scan(max_total_bytes=16)
        self.assertTrue(changed)
        self.assertTrue(result["scan_partial"])
        self.assertIn("file_changed", result["partial_reasons"])
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["summary"]["bytes_read"], 16)
        self.assertEqual([(path.stat().st_mtime_ns, path.stat().st_ctime_ns) for path in (first, second)], before)

    @unittest.skipUnless(hasattr(os, "link"), "hardlinks unavailable")
    def test_descriptor_baseline_is_shared_by_hardlink_identity(self):
        first = self.write("a")
        self.write("b")
        try:
            os.link(first, self.root / "alias")
        except OSError as error:
            self.skipTest(str(error))
        target_inode = first.stat().st_ino
        original_stat = os.fstat
        original_equal = module._Scanner.equal_files
        changed = False
        baseline_count = None

        class DescriptorStat:
            def __init__(self, info):
                self.info = info
                delta = int(changed and info.st_ino == target_inode)
                self.st_ctime_ns = info.st_ctime_ns + 1_000_000_000 + delta

            def __getattr__(self, name):
                return getattr(self.info, name)

        def change_after_comparison(scanner, left, right):
            nonlocal changed, baseline_count
            equal = original_equal(scanner, left, right)
            baseline_count = len(scanner.fd_markers)
            changed = True
            return equal

        with patch.object(module.os, "supports_dir_fd", set()), \
                patch.object(module.os, "fstat", side_effect=lambda descriptor: DescriptorStat(original_stat(descriptor))), \
                patch.object(module._Scanner, "equal_files", change_after_comparison):
            result = self.scan()
        self.assertEqual(baseline_count, 2)  # two files, three paths
        self.assertTrue(result["scan_partial"])
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["hardlink_groups"], [])
        self.assertEqual(result["summary"]["logical_duplicate_bytes"], 0)

    def test_hash_io_failure_is_partial_not_clean_absence(self):
        self.write("a")
        self.write("b")
        with patch.object(module.os, "read", side_effect=PermissionError("denied")):
            result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertIn("file_read_failed", result["partial_reasons"])
        self.assertEqual(result["group_count"], 0)

    def test_group_and_path_truncation_keep_complete_aggregate_counts(self):
        for index in range(60):
            self.write(f"a{index:03}", bytes([index]) * (index + 1))
            self.write(f"b{index:03}", bytes([index]) * (index + 1))
        result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["scan_partial"])
        self.assertEqual(result["group_count"], 60)
        self.assertEqual(len(result["groups"]), 50)
        self.assertEqual(result["groups_omitted"], 10)
        self.assertTrue(result["report_truncated"])
        self.assertEqual(result["summary"]["logical_duplicate_bytes"], sum(range(1, 61)))

    def test_group_path_cap_is_separate_from_scan_completeness(self):
        for index in range(25):
            self.write(f"copy{index:02}", b"x")
        result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["scan_partial"])
        self.assertEqual(result["groups"][0]["file_count"], 25)
        self.assertEqual(result["groups"][0]["paths_omitted"], 5)
        self.assertEqual(len(result["groups"][0]["paths"]), 20)
        self.assertTrue(result["report_truncated"])

    def test_skip_details_are_bounded_without_changing_scan_coverage(self):
        for index in range(60):
            self.write(f"d{index:02}/.git/private")
        result = self.scan()
        self.assertEqual(result["skip_count"], 60)
        self.assertEqual(len(result["skips"]), 50)
        self.assertEqual(result["skips_omitted"], 10)
        self.assertTrue(result["report_truncated"])
        self.assertFalse(result["scan_partial"])
        self.assertEqual(result["status"], "partial")

    def test_collision_comparison_cap_is_partial(self):
        self.write("a", b"a")
        self.write("b", b"b")
        self.write("c", b"c")

        class Collision:
            def update(self, _data):
                pass

            def hexdigest(self):
                return "0" * 64

        with patch.object(module.hashlib, "sha256", Collision), patch.object(module, "MAX_COMPARISONS", 1):
            result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertIn("max_comparisons", result["partial_reasons"])
        self.assertEqual(result["summary"]["comparisons"], 1)

    def test_invalid_parameters_and_exclusion_paths_are_rejected(self):
        for name in ("max_files", "max_file_bytes", "max_total_bytes", "max_entries", "max_depth"):
            for value in (True, -1, 0.5):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.scan(**{name: value})
        for name, value in (("max_files", 50001), ("max_file_bytes", 1024**3 + 1),
                            ("max_total_bytes", 1024**3 + 1), ("max_entries", 100001), ("max_depth", 129)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.scan(**{name: value})
        for excluded in ("venv", ["../private"], ["a/b"], ["a\\b"], [".."], ["."], [""], [True], ["x"] * 101):
            with self.subTest(excluded=excluded), self.assertRaises(ValueError):
                self.scan(exclude_dirs=excluded)

    def test_invalid_roots_and_root_symlink_are_rejected(self):
        file = self.write("file")
        for root in (None, "", "\0", str(file), str(self.root / "missing")):
            with self.subTest(root=root), self.assertRaises(ValueError):
                find_file_duplicates(root)
        if hasattr(os, "symlink"):
            try:
                os.symlink(self.root, self.root / "alias_root", target_is_directory=True)
            except OSError as error:
                self.skipTest(str(error))
            with self.assertRaises(ValueError):
                find_file_duplicates(str(self.root / "alias_root"))

    def test_output_is_strict_json_and_inputs_and_files_are_unchanged(self):
        a = self.write("a", b"same")
        b = self.write("b", b"same")
        params = {"exclude_dirs": ["node_modules", ".git"]}
        before = copy.deepcopy(params)
        stats_before = [(path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode) for path in (a, b)]
        result = self.scan(**params)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(params, before)
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode) for path in (a, b)], stats_before)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FileDuplicateTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"{result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
