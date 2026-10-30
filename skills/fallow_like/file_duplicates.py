"""Bounded, read-only discovery of exact file copies under one explicit root.

Size and SHA-256 are candidate filters; byte comparison confirms each reported
copy group. Hardlinks are reported separately. This is not an atomic snapshot
and logical duplicate bytes are not a prediction of reclaimable physical space.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
import stat

DEFAULT_EXCLUDE_DIRS = (".git", "node_modules", ".venv", "venv", "__pycache__")
MAX_COMPARISONS = 20_000
_CHUNK = 65_536
_DETAILS = 50
_PATHS = 20


class _Changed(Exception):
    pass


class _BudgetExceeded(Exception):
    pass


def _marker(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, "st_file_attributes", 0), getattr(info, "st_reparse_tag", 0))


def _is_reparse(info):
    return bool(getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                or getattr(info, "st_reparse_tag", 0))


def _opened_marker(info):
    # CPython 3.12 on Windows exposes creation time through path st_ctime,
    # but change time through fstat st_ctime. Compare ctime within each API.
    # Path stat may also synthesize executable permission bits from extensions
    # on Windows; retain full mode comparisons only within the same API.
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns


def _directory_identity(info):
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), _is_reparse(info)


class _Scanner:
    def __init__(self, root, root_info, limits, excluded):
        self.root = root
        self.root_info = root_info
        self.limits = limits
        self.excluded = set(excluded)
        self.root_fd = None
        self.anchored = (os.open in os.supports_dir_fd
                         and os.stat in os.supports_dir_fd
                         and os.scandir in os.supports_fd
                         and hasattr(os, "O_DIRECTORY")
                         and hasattr(os, "O_NOFOLLOW"))
        self.directories = {(): root_info}
        self.records = []
        self.reasons = set()
        self.errors, self.skips = [], []
        self.error_count = self.skip_count = 0
        self.entries = self.files = self.hashed = 0
        self.hash_bytes = self.comparison_bytes = self.comparisons = 0
        self.stop_walk = False

    def _note(self, category, reason, path, *, partial=False):
        if partial:
            self.reasons.add(reason)
        item = {"path": path or ".", "reason": reason}
        if category == "error":
            self.error_count += 1
            if len(self.errors) < _DETAILS:
                self.errors.append(item)
        else:
            self.skip_count += 1
            if len(self.skips) < _DETAILS:
                self.skips.append(item)

    def _path(self, parts):
        return os.path.join(self.root, *parts)

    @staticmethod
    def _relative(parts):
        return "/".join(parts)

    @staticmethod
    def _flags(directory=False):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_BINARY", 0)
        if directory:
            flags |= getattr(os, "O_DIRECTORY", 0)
        return flags

    def _entry_stat(self, name, parent_parts, parent_fd):
        if self.anchored:
            return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return os.lstat(self._path(parent_parts + (name,)))

    @contextmanager
    def _parent(self, parts):
        """Anchor every parent component, or revalidate it on portable fallback."""
        if self.anchored:
            descriptor = os.dup(self.root_fd)
            try:
                if _directory_identity(os.fstat(descriptor)) != _directory_identity(self.root_info):
                    raise _Changed("root identity changed")
                traversed = ()
                for name in parts:
                    child = os.open(name, self._flags(directory=True), dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = child
                    traversed += (name,)
                    expected = self.directories[traversed]
                    if _directory_identity(os.fstat(descriptor)) != _directory_identity(expected):
                        raise _Changed("parent directory changed")
                yield descriptor
            finally:
                os.close(descriptor)
        else:
            for length in range(len(parts) + 1):
                ancestor = parts[:length]
                actual = os.lstat(self._path(ancestor))
                if _directory_identity(actual) != _directory_identity(self.directories[ancestor]):
                    raise _Changed("parent directory changed")
            yield None

    @contextmanager
    def _open_file(self, record):
        parts, expected = record["parts"], record["info"]
        with self._parent(parts[:-1]) as parent_fd:
            before = self._entry_stat(parts[-1], parts[:-1], parent_fd)
            if (_is_reparse(before) or not stat.S_ISREG(before.st_mode)
                    or _marker(before) != _marker(expected)):
                raise _Changed("file changed before open")
            if self.anchored:
                descriptor = os.open(parts[-1], self._flags(), dir_fd=parent_fd)
            else:
                descriptor = os.open(self._path(parts), self._flags())
            try:
                opened = os.fstat(descriptor)
                if (_is_reparse(opened) or not stat.S_ISREG(opened.st_mode)
                        or _opened_marker(opened) != _opened_marker(before)):
                    raise _Changed("opened file differs from inventory")
                yield descriptor
                after = os.fstat(descriptor)
                current = self._entry_stat(parts[-1], parts[:-1], parent_fd)
                if (_is_reparse(after) or _is_reparse(current)
                        or _marker(after) != _marker(opened) or _marker(current) != _marker(before)):
                    raise _Changed("file changed during read")
            finally:
                os.close(descriptor)

    def walk(self, parts=(), descriptor=None, depth=0):
        if self.stop_walk:
            return
        expected = self.directories[parts]
        try:
            before = os.fstat(descriptor) if self.anchored else os.lstat(self._path(parts))
            if _is_reparse(before) or _marker(before) != _marker(expected):
                raise _Changed("directory changed before enumeration")
            entries = []
            with os.scandir(descriptor if self.anchored else self._path(parts)) as iterator:
                for entry in iterator:
                    if self.entries >= self.limits["max_entries"]:
                        self._note("skip", "max_entries", self._relative(parts), partial=True)
                        self.stop_walk = True
                        break
                    self.entries += 1
                    try:
                        info = self._entry_stat(entry.name, parts, descriptor)
                        entries.append((entry.name, info))
                    except OSError:
                        self._note("error", "entry_stat_failed", self._relative(parts + (entry.name,)), partial=True)
            for name, info in sorted(entries, key=lambda item: item[0]):
                child_parts = parts + (name,)
                relative = self._relative(child_parts)
                if _is_reparse(info):
                    self._note("skip", "reparse_point_excluded", relative)
                elif stat.S_ISLNK(info.st_mode):
                    self._note("skip", "symlink_excluded", relative)
                elif stat.S_ISDIR(info.st_mode):
                    if name in self.excluded:
                        self._note("skip", "directory_excluded", relative)
                    elif depth >= self.limits["max_depth"]:
                        self._note("skip", "max_depth", relative, partial=True)
                    elif not self.stop_walk:
                        self.directories[child_parts] = info
                        child_fd = None
                        try:
                            if self.anchored:
                                child_fd = os.open(name, self._flags(directory=True), dir_fd=descriptor)
                            self.walk(child_parts, child_fd, depth + 1)
                        except OSError:
                            self._note("error", "directory_open_failed", relative, partial=True)
                        finally:
                            if child_fd is not None:
                                os.close(child_fd)
                elif stat.S_ISREG(info.st_mode):
                    if self.files >= self.limits["max_files"]:
                        self._note("skip", "max_files", relative, partial=True)
                        self.stop_walk = True
                        break
                    self.files += 1
                    identity = (info.st_dev, info.st_ino) if info.st_ino else ("path", relative)
                    if not info.st_ino:
                        self.reasons.add("file_identity_unavailable")
                    self.records.append({"parts": child_parts, "info": info,
                                         "identity": identity, "path": relative})
                    if info.st_size > self.limits["max_file_bytes"]:
                        self._note("skip", "max_file_bytes", relative, partial=True)
                else:
                    self._note("skip", "special_file_excluded", relative)
            after = os.fstat(descriptor) if self.anchored else os.lstat(self._path(parts))
            if _marker(after) != _marker(expected):
                raise _Changed("directory changed during enumeration")
        except _Changed:
            self._note("error", "directory_changed", self._relative(parts), partial=True)
        except OSError:
            self._note("error", "directory_scan_failed", self._relative(parts), partial=True)

    def _remaining(self):
        return self.limits["max_total_bytes"] - self.hash_bytes - self.comparison_bytes

    def _read(self, descriptor, count, category):
        output = bytearray()
        while len(output) < count:
            available = self._remaining()
            if available <= 0:
                raise _BudgetExceeded
            chunk = os.read(descriptor, min(count - len(output), available))
            if category == "hash":
                self.hash_bytes += len(chunk)
            else:
                self.comparison_bytes += len(chunk)
            if not chunk:
                raise _Changed("file shortened during read")
            output.extend(chunk)
        return bytes(output)

    def hash_file(self, record):
        digest = hashlib.sha256()
        with self._open_file(record) as descriptor:
            remaining = record["info"].st_size
            while remaining:
                chunk = self._read(descriptor, min(_CHUNK, remaining), "hash")
                digest.update(chunk)
                remaining -= len(chunk)
        self.hashed += 1
        return digest.hexdigest()

    def equal_files(self, left, right):
        if self.comparisons >= MAX_COMPARISONS:
            raise _BudgetExceeded("max_comparisons")
        self.comparisons += 1
        equal = True
        with self._open_file(left) as first, self._open_file(right) as second:
            remaining = left["info"].st_size
            while remaining:
                available = self._remaining() // 2
                if not available:
                    raise _BudgetExceeded
                count = min(_CHUNK, remaining, available)
                if self._read(first, count, "comparison") != self._read(second, count, "comparison"):
                    equal = False
                    break
                remaining -= count
        return equal

    def _failed_read(self, error, record):
        if isinstance(error, _BudgetExceeded):
            reason = "max_comparisons" if str(error) == "max_comparisons" else "max_total_bytes"
            self._note("skip", reason, record["path"], partial=True)
        else:
            self._note("error", "file_changed" if isinstance(error, _Changed) else "file_read_failed",
                       record["path"], partial=True)

    def finish(self):
        identities = {}
        for record in self.records:
            identities.setdefault(record["identity"], []).append(record)
        candidates = {}
        for identity, records in identities.items():
            first = records[0]
            if any(_marker(record["info"]) != _marker(first["info"]) for record in records[1:]):
                self._note("error", "file_changed", first["path"], partial=True)
                continue
            if first["info"].st_size <= self.limits["max_file_bytes"]:
                candidates.setdefault(first["info"].st_size, []).append(identity)

        buckets = {}
        exhausted = False
        for size, keys in sorted(candidates.items()):
            if len(keys) < 2:
                continue
            for identity in sorted(keys, key=lambda key: identities[key][0]["path"]):
                record = identities[identity][0]
                try:
                    digest = self.hash_file(record)
                    buckets.setdefault((size, digest), []).append(identity)
                except (OSError, _Changed, _BudgetExceeded) as error:
                    self._failed_read(error, record)
                    if isinstance(error, _BudgetExceeded):
                        exhausted = True
                        break
            if exhausted:
                break

        confirmed = []
        if not exhausted:
            for (size, digest), keys in sorted(buckets.items()):
                partitions = []
                for identity in keys:
                    record = identities[identity][0]
                    placed = False
                    for partition in partitions:
                        try:
                            if self.equal_files(identities[partition[0]][0], record):
                                partition.append(identity)
                                placed = True
                                break
                        except (OSError, _Changed, _BudgetExceeded) as error:
                            self._failed_read(error, record)
                            if isinstance(error, _BudgetExceeded):
                                exhausted = True
                            placed = True  # no proof for this candidate
                            break
                    if not placed:
                        partitions.append([identity])
                    if exhausted:
                        break
                confirmed.extend((size, digest, group) for group in partitions if len(group) > 1)
                if exhausted:
                    break

        # Revalidate all known paths and directory identities after content work.
        # This detects observed races; it cannot turn the run into an atomic snapshot.
        valid = {}
        for identity, records in identities.items():
            for record in records:
                try:
                    with self._parent(record["parts"][:-1]) as parent_fd:
                        current = self._entry_stat(record["parts"][-1], record["parts"][:-1], parent_fd)
                    if _is_reparse(current) or _marker(current) != _marker(record["info"]):
                        raise _Changed
                    valid.setdefault(identity, []).append(record)
                except (OSError, _Changed):
                    self._note("error", "file_changed", record["path"], partial=True)
        detached = set()
        for parts, expected in self.directories.items():
            try:
                if self.anchored and parts:
                    with self._parent(parts[:-1]) as parent_fd:
                        current = self._entry_stat(parts[-1], parts[:-1], parent_fd)
                else:
                    current = os.lstat(self._path(parts))
                if _directory_identity(current) != _directory_identity(expected):
                    detached.add(parts)
                if _marker(current) != _marker(expected):
                    raise _Changed
            except (OSError, _Changed):
                self._note("error", "directory_changed", self._relative(parts), partial=True)
                # Missing/unreachable attachment also invalidates this subtree.
                # A metadata-only change keeps stable file evidence available.
                try:
                    attached = os.lstat(self._path(parts))
                    if _directory_identity(attached) != _directory_identity(expected):
                        detached.add(parts)
                except OSError:
                    detached.add(parts)
        if detached:
            valid = {
                identity: attached_records
                for identity, records in valid.items()
                if (attached_records := [
                    record for record in records
                    if not any(record["parts"][:length] in detached
                               for length in range(len(record["parts"])))
                ])
            }

        groups = []
        logical_bytes = 0
        path_truncated = False
        for size, digest, keys in confirmed:
            paths = sorted(valid[key][0]["path"] for key in keys if key in valid)
            if len(paths) < 2:
                continue
            duplicate_bytes = size * (len(paths) - 1)
            logical_bytes += duplicate_bytes
            path_truncated |= len(paths) > _PATHS
            groups.append({"match": "exact_bytes", "size_bytes": size, "sha256": digest,
                           "file_count": len(paths), "paths": paths[:_PATHS],
                           "paths_omitted": max(0, len(paths) - _PATHS),
                           "logical_duplicate_bytes": duplicate_bytes})
        groups.sort(key=lambda group: (-group["logical_duplicate_bytes"], group["paths"]))
        hardlinks = []
        for records in valid.values():
            if len(records) > 1:
                paths = sorted(record["path"] for record in records)
                path_truncated |= len(paths) > _PATHS
                hardlinks.append({"size_bytes": records[0]["info"].st_size,
                                  "path_count": len(paths), "paths": paths[:_PATHS],
                                  "paths_omitted": max(0, len(paths) - _PATHS)})
        hardlinks.sort(key=lambda group: group["paths"])
        truncated = (path_truncated or len(groups) > _DETAILS or len(hardlinks) > _DETAILS
                     or self.error_count > _DETAILS or self.skip_count > _DETAILS)
        return {
            "schema": "botte.file-duplicates/v1", "root": self.root,
            "status": "partial" if self.reasons or truncated else "complete",
            "scan_partial": bool(self.reasons), "report_truncated": bool(truncated),
            "partial_reasons": sorted(self.reasons), "atomic_snapshot": False,
            "filesystem_access": "anchored_dir_fd" if self.anchored else "path_checks",
            "excluded_dirs": sorted(self.excluded), "limits": self.limits,
            "summary": {"entries_examined": self.entries, "files_seen": self.files,
                        "unique_files": len(identities), "hashed_files": self.hashed,
                        "bytes_read": self.hash_bytes + self.comparison_bytes,
                        "hash_bytes_read": self.hash_bytes,
                        "comparison_bytes_read": self.comparison_bytes,
                        "comparisons": self.comparisons, "logical_duplicate_bytes": logical_bytes},
            "groups": groups[:_DETAILS], "group_count": len(groups),
            "groups_omitted": max(0, len(groups) - _DETAILS),
            "hardlink_groups": hardlinks[:_DETAILS], "hardlink_group_count": len(hardlinks),
            "hardlink_groups_omitted": max(0, len(hardlinks) - _DETAILS),
            "errors": self.errors, "error_count": self.error_count,
            "errors_omitted": max(0, self.error_count - _DETAILS),
            "skips": self.skips, "skip_count": self.skip_count,
            "skips_omitted": max(0, self.skip_count - _DETAILS),
        }


def find_file_duplicates(root: str, *, max_files=5000, max_file_bytes=16 * 1024 * 1024,
                         max_total_bytes=64 * 1024 * 1024, max_entries=20000,
                         max_depth=20, exclude_dirs=None) -> dict:
    """Return bounded exact-copy and hardlink groups; never modify the tree.

    A complete scan covers the declared exclusions only. Limits, read failures
    or observed changes produce ``scan_partial=True``. Detail truncation is a
    separate flag and does not discard aggregate confirmed-group counts.
    """
    if type(root) is not str or not root or "\0" in root:
        raise ValueError("root must be an explicit existing directory path")
    parameters = {
        "max_files": (max_files, 1, 50000),
        "max_file_bytes": (max_file_bytes, 1, 1024**3),
        "max_total_bytes": (max_total_bytes, 1, 1024**3),
        "max_entries": (max_entries, 1, 100000),
        "max_depth": (max_depth, 0, 128),
    }
    for name, (value, minimum, maximum) in parameters.items():
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer from {minimum} through {maximum}")
    names = list(DEFAULT_EXCLUDE_DIRS) if exclude_dirs is None else exclude_dirs
    if (not isinstance(names, list) or len(names) > 100
            or any(type(name) is not str or not name or len(name) > 255
                   or name in (".", "..") or any(char in name for char in ("/", "\\", "\0"))
                   for name in names)):
        raise ValueError("exclude_dirs must contain at most 100 directory names, not paths")
    absolute = os.path.abspath(root)
    try:
        root_info = os.lstat(absolute)
    except OSError as error:
        raise ValueError("root must be an explicit existing directory path") from error
    if _is_reparse(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("root must be a directory, not a symlink, reparse point or file")
    limits = {name: value[0] for name, value in parameters.items()}
    limits["max_comparisons"] = MAX_COMPARISONS
    scanner = _Scanner(absolute, root_info, limits, names)
    try:
        if scanner.anchored:
            scanner.root_fd = os.open(absolute, scanner._flags(directory=True))
        scanner.walk(descriptor=scanner.root_fd)
        return scanner.finish()
    except OSError:
        scanner._note("error", "root_open_failed", ".", partial=True)
        return scanner.finish()
    finally:
        if scanner.root_fd is not None:
            os.close(scanner.root_fd)
