"""Conservative host-memory admission shared by cooperating local supervisors.

Reservations are budgets, not OS memory limits. Count full budgets in addition
to OS usage; never reclaim a reservation merely because a timestamp expired.
Use one shared state path for every participating supervisor on a host.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import json
import math
import os
from pathlib import Path
import platform
import tempfile
import time

GiB = 1024 ** 3
MAX_SAMPLE_AGE = 2.0


def default_state_path():
    configured = os.environ.get("BOTTE_RESOURCE_STATE")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            raise ValueError("BOTTE_RESOURCE_STATE must be an absolute host-local path")
        return path
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
                or (Path.home() / ".local" / "state"))
    return base / "botte-secrete" / "host-memory.json"


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("invalid memory byte count")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate memory state field")
        result[key] = value
    return result


def _cgroup_v2(total, available):
    """Apply every visible cgroup-v2 ancestor; no swap is counted as RAM."""
    memberships = Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
    if any("memory" in line.split(":")[1].split(",") for line in memberships):
        raise OSError("cgroup-v1 memory accounting is unsupported")
    unified = next((line[3:] for line in memberships if line.startswith("0::")), None)
    if unified is None:
        return total, available
    mounts = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    mounted = [line.split(" - ", 1)[0].split() for line in mounts
               if " - cgroup2 " in line]
    if not mounted:
        # A container can hide the mount while /proc/meminfo still reports
        # host RAM. Unknown cgroup headroom must not look like unlimited RAM.
        raise OSError("cgroup-v2 memory bounds are not observable")
    fields = mounted[0]
    mount_root, mount = fields[3], Path(fields[4])
    if "\\" in mount_root or "\\" in str(mount) or ".." in Path(unified).parts:
        raise OSError("unreadable cgroup mount mapping")
    if unified == "/":
        current = mount
    else:
        try:
            relative = Path(unified).relative_to(mount_root)
        except ValueError as error:
            raise OSError("unreadable cgroup membership") from error
        current = mount / relative
    while True:
        limit_path, used_path = current / "memory.max", current / "memory.current"
        if limit_path.exists() or used_path.exists():
            limit_text = limit_path.read_text(encoding="utf-8").strip()
            used = int(used_path.read_text(encoding="utf-8").strip())
            if used < 0:
                raise ValueError("invalid cgroup usage")
            if limit_text != "max":
                limit = int(limit_text)
                if limit <= 0:
                    raise ValueError("invalid cgroup limit")
                total = min(total, limit)
                available = min(available, max(0, limit - used))
        if current == mount:
            break
        current = current.parent
    return total, available


def probe_memory():
    """Read physical headroom and Windows commit headroom, without subprocesses."""
    system = platform.system()
    if system == "Windows":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
                (name, ctypes.c_uint64) for name in ("total", "available", "page_total",
                                                    "page_available", "virtual_total",
                                                    "virtual_available", "extended")]
        status = Status()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("Windows memory measurement failed")
        total, available, commit = status.total, status.available, status.page_available
    elif system == "Linux":
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts[0] in {"MemTotal:", "MemAvailable:"}:
                if len(parts) != 3 or parts[2] != "kB":
                    raise ValueError("invalid Linux memory units")
                values[parts[0][:-1]] = int(parts[1]) * 1024
        total, available = _cgroup_v2(values["MemTotal"], values["MemAvailable"])
        commit = None
    else:
        raise OSError("unsupported memory measurement platform")
    return {"total_bytes": total, "available_bytes": available,
            "commit_available_bytes": commit, "commit_required": system == "Windows",
            "source": system.lower(), "measured_monotonic": time.monotonic(),
            "measured_at_utc": datetime.now(timezone.utc).isoformat()}


@contextmanager
def _file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as initial:
            initial.write(b"0")
    except FileExistsError:
        pass
    with path.open("r+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class HostMemoryGuard:
    def __init__(self, path=None, probe=probe_memory, system_reserve_bytes=2 * GiB):
        self.path = Path(path) if path is not None else default_state_path()
        if not self.path.is_absolute():
            raise ValueError("resource state path must be absolute")
        self.probe = probe
        self.system_reserve_bytes = _integer(system_reserve_bytes, 1)

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not 1 <= len(key) <= 4096:
            raise ValueError("invalid memory reservation key")
        return key

    def _load(self):
        if not self.path.exists():
            # Byte 1 of the stable lock inode records that a registry existed.
            # Losing only the JSON must not silently erase active budgets.
            if Path(str(self.path) + ".lock").stat().st_size > 1:
                raise OSError("initialized memory reservation state is missing")
            return {"schema_version": 1, "reservations": {}}
        if self.path.stat().st_size > 2 * 1024 ** 2:
            raise ValueError("memory reservation state exceeds limit")
        doc = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite state")))
        if (not isinstance(doc, dict) or doc.get("schema_version") != 1
                or type(doc.get("schema_version")) is not int
                or not isinstance(doc.get("reservations"), dict)):
            raise ValueError("invalid memory reservation state")
        for key, lease in doc["reservations"].items():
            self._key(key)
            if not isinstance(lease, dict):
                raise ValueError("invalid memory reservation")
            _integer(lease.get("requested_bytes"), 1)
        return doc

    def _save(self, doc):
        staged = None
        try:
            # Mark before writing: uncertainty after any persistence failure
            # blocks admission until the operator reconciles the state.
            with Path(str(self.path) + ".lock").open("r+b") as marker:
                marker.seek(1)
                marker.write(b"1")
                marker.flush()
                os.fsync(marker.fileno())
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".host-memory-", delete=False) as handle:
                staged = Path(handle.name)
                json.dump(doc, handle, separators=(",", ":"), allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, self.path)
            staged = None
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    def _measure(self, doc):
        sample = self.probe()
        if not isinstance(sample, dict):
            raise ValueError("invalid memory measurement")
        total = _integer(sample.get("total_bytes"), 1)
        available = _integer(sample.get("available_bytes"))
        if available > total or sample.get("source") not in {"windows", "linux"}:
            raise ValueError("invalid memory measurement")
        measured = sample.get("measured_monotonic")
        if (isinstance(measured, bool) or not isinstance(measured, (int, float))
                or not math.isfinite(measured) or not 0 <= time.monotonic() - measured <= MAX_SAMPLE_AGE):
            raise ValueError("stale memory measurement")
        stamp = sample.get("measured_at_utc")
        if not isinstance(stamp, str):
            raise ValueError("missing memory measurement timestamp")
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError("memory timestamp must be UTC")
        commit_required = sample.get("source") == "windows"
        if sample.get("commit_required") is not commit_required:
            raise ValueError("invalid commit measurement requirement")
        commit = sample.get("commit_available_bytes")
        if commit_required or commit is not None:
            _integer(commit)
        reserved = sum(lease["requested_bytes"] for lease in doc["reservations"].values())
        margin = max(self.system_reserve_bytes, (total + 9) // 10)
        return {"total_bytes": total, "available_bytes": available,
                "commit_available_bytes": commit, "reserved_bytes": reserved,
                "reservation_count": len(doc["reservations"]),
                "system_reserve_bytes": margin,
                "measured_at_utc": sample.get("measured_at_utc"), "source": sample["source"]}

    @staticmethod
    def _decision(metrics, extra=0):
        required = metrics["reserved_bytes"] + metrics["system_reserve_bytes"] + extra
        reason = "admitted"
        if required > metrics["available_bytes"]:
            reason = "insufficient_ram"
        elif (metrics["commit_available_bytes"] is not None
              and required > metrics["commit_available_bytes"]):
            reason = "insufficient_commit"
        return {"allowed": reason == "admitted", "reason": reason, **metrics}

    def reserve(self, key, requested_bytes):
        """Persist a full budget before allowing execution; same-key retries are idempotent."""
        try:
            self._key(key)
            _integer(requested_bytes, 1)
            with _file_lock(Path(str(self.path) + ".lock")):
                doc = self._load()
                old = doc["reservations"].get(key)
                if old and old["requested_bytes"] != requested_bytes:
                    return {"allowed": False, "reason": "reservation_conflict"}
                metrics = self._measure(doc)
                result = self._decision(metrics, 0 if old else requested_bytes)
                if result["allowed"] and old is None:
                    doc["reservations"][key] = {"requested_bytes": requested_bytes}
                    self._save(doc)
                    result["reserved_bytes"] += requested_bytes
                    result["reservation_count"] += 1
                return result
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return {"allowed": False, "reason": "resource_state_unavailable"}

    def check(self, key):
        """Remeasure immediately before launch; an unknown/missing lease cannot admit."""
        try:
            self._key(key)
            with _file_lock(Path(str(self.path) + ".lock")):
                doc = self._load()
                if key not in doc["reservations"]:
                    return {"allowed": False, "reason": "reservation_missing"}
                return self._decision(self._measure(doc))
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return {"allowed": False, "reason": "resource_state_unavailable"}

    def release(self, key):
        """Release only after verified completion or operator reconciliation; failures propagate."""
        self._key(key)
        with _file_lock(Path(str(self.path) + ".lock")):
            doc = self._load()
            if key in doc["reservations"]:
                del doc["reservations"][key]
                self._save(doc)

    def retain_many(self, reservations):
        """Recover already-occupied budgets; never admit work or shrink a budget.

        Call only from a supervisor's persistent occupied/unknown-job recovery.
        Recording these budgets must succeed even when current headroom is low.
        """
        if not isinstance(reservations, dict):
            raise ValueError("invalid retained memory reservations")
        for key, budget in reservations.items():
            self._key(key)
            _integer(budget, 1)
        with _file_lock(Path(str(self.path) + ".lock")):
            doc = self._load()
            changed = False
            for key, budget in reservations.items():
                old = doc["reservations"].get(key, {}).get("requested_bytes", 0)
                if budget > old:
                    doc["reservations"][key] = {"requested_bytes": budget}
                    changed = True
            if changed:
                self._save(doc)

    def snapshot(self, *, include_reservations=False):
        try:
            with _file_lock(Path(str(self.path) + ".lock")):
                doc = self._load()
                try:
                    result = self._decision(self._measure(doc))
                except (OSError, ValueError, TypeError, KeyError, OverflowError):
                    # The local owner still needs valid reservation identities
                    # to reconcile stopped work when telemetry is unavailable.
                    result = {"allowed": False, "reason": "resource_state_unavailable"}
                if include_reservations:
                    result["reservations"] = [{"key": key, **lease}
                                              for key, lease in doc["reservations"].items()]
                return result
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return {"allowed": False, "reason": "resource_state_unavailable"}


def main(argv=None):
    """Local-owner inspection/reconciliation only; no network endpoint or auto-reclaim."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Inspect and reconcile host-local RAM reservations.")
    parser.add_argument("--state", type=Path, help="Absolute shared host-local registry path")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Read live headroom and reservation keys/budgets")
    release = commands.add_parser("release", help="Release one reservation after verified execution stop")
    release.add_argument("key")
    release.add_argument("--stopped-confirmed", action="store_true")
    for command in (status, release):
        command.add_argument("--state", dest="command_state", type=Path)
    args = parser.parse_args(argv)
    if args.command == "release" and not args.stopped_confirmed:
        parser.error("Verify that this execution has stopped, then pass --stopped-confirmed.")
    try:
        guard = HostMemoryGuard(args.command_state or args.state)
        if args.command == "status":
            result = guard.snapshot(include_reservations=True)
            print(json.dumps(result, ensure_ascii=True, allow_nan=False))
            return 0 if result["allowed"] else 1
        guard.release(args.key)
        print(json.dumps({"released": True, "key": args.key}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print(json.dumps({"released": False, "reason": "resource_state_unavailable"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
