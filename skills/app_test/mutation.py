"""Bounded Python mutation checks in disposable project copies.

``run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"],
command=[sys.executable, "-m", "unittest", "test_subject"])`` first observes a
passing baseline, then runs one-site AST mutations in fresh copies. Explicit
support paths can supply package files. Only selected regular files are copied;
symlinks and path escapes are rejected. Original files are never written by the harness itself.

The command adapter recognizes standard unittest completion evidence. Other
frameworks can provide ``runner(workspace, timeout_seconds) -> {status, ...}``,
where status is passed/failed/incomplete/not_run. Callback deadlines are
cooperative. A disposable cwd is NOT an OS security sandbox: selected tests and
commands must be trusted, and may access the machine or network like any test.
"""

from __future__ import annotations

import ast
import hashlib
import io
from itertools import islice
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time
import tokenize
from typing import Callable, Sequence

_MAX_SOURCE_BYTES = 128 * 1024
_MAX_AST_NODES = 10000
_MAX_FILES = 128
_MAX_FILE_BYTES = 1024 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_BYTES = 1024 * 1024
_TAIL_BYTES = 4096
_COMPARE = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE,
            ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
            ast.Is: ast.IsNot, ast.IsNot: ast.Is,
            ast.In: ast.NotIn, ast.NotIn: ast.In}
_RAN = re.compile(r"^Ran (\d{1,10}) tests? in [^\r\n]+\r?$", re.MULTILINE)
_OK = re.compile(r"^OK(?: \(skipped=(\d{1,10})\))?\r?$", re.MULTILINE)
_FAILED = re.compile(r"^FAILED \(([^\r\n]*)\)\r?$", re.MULTILINE)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _integer(value: int, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _seconds(value: float, name: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and positive, at most {maximum}")
    return float(value)


def generate_mutants(source: str, *, max_mutants: int = 12) -> list[dict]:
    """Generate deterministic single-site comparison, boolean or integer changes.

    Candidate order is source position, then AST traversal order. Integers are
    changed by +1 (booleans are separate); strings/docstrings are not mutated.
    Each result includes replacement source. This is a small operator subset,
    not exhaustive mutation coverage, and it may contain equivalent mutants.
    """
    _integer(max_mutants, "max_mutants", 1, 128)
    if not isinstance(source, str) or len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        raise ValueError("source must be UTF-8 text at most 128 KiB")
    try:
        tree = ast.parse(source)
        nodes = list(ast.walk(tree))
        if len(nodes) > _MAX_AST_NODES:
            raise ValueError("source AST exceeds node limit")
    except (SyntaxError, RecursionError) as error:
        raise ValueError("source is not supported Python syntax") from error
    sites = []
    for index, node in enumerate(nodes):
        if isinstance(node, ast.Compare):
            for op_index, op in enumerate(node.ops):
                if type(op) in _COMPARE:
                    sites.append((node.lineno, node.col_offset, index, op_index, "comparison"))
        elif isinstance(node, ast.Constant) and type(node.value) is bool:
            sites.append((node.lineno, node.col_offset, index, 0, "boolean"))
        elif isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= 10**12:
            sites.append((node.lineno, node.col_offset, index, 0, "integer_plus_one"))
    # AST positions use UTF-8 byte columns; tokenize positions use characters.
    # Edit only the selected lexical token so comments, headers and formatting
    # cannot become an unrelated reason for a mutant's test failure.
    raw = source.encode("utf-8")
    lines = source.splitlines(keepends=True)
    starts = [0]
    for text in lines:
        starts.append(starts[-1] + len(text.encode("utf-8")))

    def ast_offset(line, column):
        return starts[line - 1] + column

    def token_offset(position):
        line, column = position
        return starts[line - 1] + len(lines[line - 1][:column].encode("utf-8"))

    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    mutants = []
    for line, column, index, op_index, kind in sorted(sites)[:max_mutants]:
        target = nodes[index]
        if kind == "comparison":
            before = type(target.ops[op_index]).__name__
            after = _COMPARE[type(target.ops[op_index])].__name__
            description = f"{before} -> {after}"
            left = target.left if op_index == 0 else target.comparators[op_index - 1]
            right = target.comparators[op_index]
            lower = ast_offset(left.end_lineno, left.end_col_offset)
            upper = ast_offset(right.lineno, right.col_offset)
            operator_tokens = [token for token in tokens
                               if token.type in (tokenize.OP, tokenize.NAME)
                               and lower <= token_offset(token.start) < upper]
            spelling = {"Eq": "==", "NotEq": "!=", "Lt": "<", "LtE": "<=",
                        "Gt": ">", "GtE": ">=", "Is": "is", "IsNot": "not",
                        "In": "in", "NotIn": "not"}[before]
            matches = [token for token in operator_tokens if token.string == spelling]
            if len(matches) != 1:
                continue  # Unsupported token shape is not guessed.
            token = matches[0]
            start, end = token_offset(token.start), token_offset(token.end)
            replacement = {"Eq": "!=", "NotEq": "==", "Lt": "<=", "LtE": "<",
                           "Gt": ">=", "GtE": ">", "Is": "is not", "IsNot": "",
                           "In": "not in", "NotIn": ""}[before]
        else:
            start = ast_offset(target.lineno, target.col_offset)
            end = ast_offset(target.end_lineno, target.end_col_offset)
            # Older Python ASTs can give a formatted-value constant the span
            # of its entire f-string. Never replace that larger expression.
            try:
                lexical_value = ast.literal_eval(raw[start:end].decode("utf-8"))
            except (SyntaxError, ValueError, RecursionError):
                continue
            if type(lexical_value) is not type(target.value) or lexical_value != target.value:
                continue
            if kind == "boolean":
                description = f"{target.value} -> {not target.value}"
                replacement = str(not target.value)
            else:
                description = f"{target.value} -> {target.value + 1}"
                replacement = str(target.value + 1)
        altered = raw[:start] + replacement.encode("utf-8") + raw[end:]
        try:
            replacement_source = altered.decode("utf-8")
            compile(replacement_source, "<mutation>", "exec")
        except (SyntaxError, ValueError, RecursionError):
            continue
        sha = _digest(altered)
        mutants.append({"id": f"m{len(mutants) + 1:03d}-{sha[:12]}",
                        "kind": kind, "line": line, "column": column,
                        "description": description, "sha256": sha,
                        "source": replacement_source})
    return mutants


def _relative(value: str, name: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError(f"{name} must be a relative path using forward slashes")
    path = Path(value)
    if path.is_absolute() or any(part in ("..", ".") for part in value.split("/")) or ":" in value:
        raise ValueError(f"{name} must remain inside the project")
    return path


def _snapshot(root: Path, selected: Sequence[str], deadline: float) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total = 0
    entries = 0

    def add(path: Path) -> None:
        nonlocal total, entries
        entries += 1
        if entries > 512 or len(path.relative_to(root).parts) > 16:
            raise ValueError("selected directory traversal exceeds entry/depth limit")
        if time.monotonic() >= deadline:
            raise ValueError("selected file snapshot time budget exhausted")
        relative = path.relative_to(root).as_posix()
        if relative in files:
            return
        # Inspect every component: a selected child of a symlink is rejected too.
        current = root
        for part in path.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("selected paths must not contain symlinks")
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            # Do not materialize an unbounded directory before enforcing limits.
            with os.scandir(path) as listing:
                children = list(islice(listing, 514 - entries))
            if len(children) > 512 - entries:
                raise ValueError("selected directory traversal exceeds entry limit")
            for child in sorted(children, key=lambda item: item.name):
                add(Path(child.path))
            return
        if not stat.S_ISREG(mode):
            raise ValueError("selected paths must contain regular files only")
        if len(files) >= _MAX_FILES:
            raise ValueError("selected file count exceeds limit")
        with path.open("rb") as stream:
            data = stream.read(_MAX_FILE_BYTES + 1)
        if len(data) > _MAX_FILE_BYTES:
            raise ValueError("selected file exceeds 1 MiB limit")
        total += len(data)
        if total > _MAX_TOTAL_BYTES:
            raise ValueError("selected files exceed 8 MiB limit")
        files[relative] = data

    for value in selected:
        relative = _relative(value, "selected path")
        path = root / relative
        try:
            add(path)
        except OSError as error:
            raise ValueError("selected path is missing or unreadable") from error
    return files


def _output_record(stream) -> tuple[dict, str]:
    stream.seek(0)
    data = stream.read(_MAX_OUTPUT_BYTES + 1)
    # The monitor stops an oversized producer. Hash all bytes actually written
    # with bounded memory, rather than calling the retained tail a full hash.
    sha = hashlib.sha256(data)
    size = len(data)
    tail = data[-_TAIL_BYTES:]
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        sha.update(chunk)
        size += len(chunk)
        tail = (tail + chunk)[-_TAIL_BYTES:]
    return {"bytes": size, "sha256": sha.hexdigest(),
            "tail": tail.decode("utf-8", errors="replace"),
            "tail_truncated": size > _TAIL_BYTES}, data.decode("utf-8", errors="replace")


def _stop(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        pass
    proc.wait()


def run_unittest_command(command: Sequence[str], workspace: Path, timeout_seconds: float) -> dict:
    """Run an explicit argv and recognize a standard unittest transcript.

    A nonzero exit without assertion-failure completion evidence is inconclusive,
    not a killed mutant. Import errors, timeouts, empty or all-skipped suites do
    not qualify a passing baseline. Logs are bounded tails plus full hashes.
    """
    if isinstance(command, (str, bytes)) or not isinstance(command, (list, tuple)) or not 1 <= len(command) <= 64 or not all(isinstance(x, str) and "\x00" not in x and len(x) <= 8192 for x in command) or not command[0]:
        raise ValueError("command must be a nonempty bounded argv without NUL")
    timeout_seconds = _seconds(timeout_seconds, "timeout_seconds", 600)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            proc = subprocess.Popen(list(command), cwd=workspace, env=env,
                                    stdin=subprocess.DEVNULL, stdout=stdout,
                                    stderr=stderr, start_new_session=os.name == "posix")
        except OSError:
            return {"status": "not_run", "reason": "command_launch_failed", "exit": None}
        reason = None
        while proc.poll() is None:
            if time.monotonic() - started >= timeout_seconds:
                reason = "timeout"
                _stop(proc)
                break
            if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > _MAX_OUTPUT_BYTES:
                reason = "output_limit"
                _stop(proc)
                break
            time.sleep(0.01)
        out_record, out = _output_record(stdout)
        err_record, err = _output_record(stderr)
    result = {"status": "incomplete", "exit": proc.returncode,
              "duration_ms": round((time.monotonic() - started) * 1000, 3),
              "stdout": out_record, "stderr": err_record}
    if reason or out_record["bytes"] + err_record["bytes"] > _MAX_OUTPUT_BYTES:
        result["reason"] = reason or "output_limit"
        return result
    transcript = out + "\n" + err
    counts = _RAN.findall(transcript)
    okay = _OK.findall(transcript)
    failed = _FAILED.findall(transcript)
    if len(counts) != 1 or int(counts[0]) < 1 or len(okay) + len(failed) != 1:
        result["reason"] = "unittest_completion_unavailable"
        return result
    result["tests_run"] = int(counts[0])
    if okay and proc.returncode == 0:
        skipped = int(okay[0]) if okay[0] else 0
        if skipped < result["tests_run"]:
            result.update(status="passed", reason="unittest_passed")
        else:
            result["reason"] = "all_tests_skipped"
    elif failed and proc.returncode != 0:
        pairs = [re.fullmatch(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d{1,10})", token)
                 for token in failed[0].split(", ")]
        if any(pair is None for pair in pairs) or len({pair.group(1) for pair in pairs}) != len(pairs):
            result["reason"] = "unsupported_unittest_failure_summary"
            return result
        fields = {pair.group(1): pair.group(2) for pair in pairs}
        if int(fields.get("failures", "0")) > 0 and int(fields.get("errors", "0")) == 0:
            result.update(status="failed", reason="unittest_assertion_failure")
        else:
            result["reason"] = "unittest_error_or_unsupported_failure"
    else:
        result["reason"] = "inconsistent_exit_and_completion"
    return result


def run_mutation_checks(project_root: str | Path, source_path: str, *,
                        test_paths: Sequence[str], command: Sequence[str] | None = None,
                        runner: Callable | None = None, support_paths: Sequence[str] = (),
                        max_mutants: int = 12, timeout_seconds: float = 10,
                        max_seconds: float = 120) -> dict:
    """Observe a baseline and bounded mutants in fresh disposable copies.

    ``runner(workspace, timeout_seconds)`` must return an explicit status, and
    honor the cooperative timeout. Callback exceptions or invalid results become
    inconclusive. At most ``1 + max_mutants`` test executions occur. A survivor is
    a gap candidate for this operator and test set, not proof of a product bug.
    """
    started = time.monotonic()
    _integer(max_mutants, "max_mutants", 1, 128)
    timeout_seconds = _seconds(timeout_seconds, "timeout_seconds", 600)
    max_seconds = _seconds(max_seconds, "max_seconds", 600)
    if (command is None) == (runner is None) or (runner is not None and not callable(runner)):
        raise ValueError("provide exactly one command or callable runner")
    if isinstance(test_paths, (str, bytes)) or not isinstance(test_paths, (list, tuple)) or not test_paths:
        raise ValueError("test_paths must be a nonempty list or tuple")
    if isinstance(support_paths, (str, bytes)) or not isinstance(support_paths, (list, tuple)):
        raise ValueError("support_paths must be a list or tuple")
    if not isinstance(project_root, (str, Path)):
        raise ValueError("project_root must be a path")
    original_root = Path(project_root)
    if original_root.is_symlink():
        raise ValueError("project root must not be a symlink")
    root = original_root.resolve()
    if not root.is_dir():
        raise ValueError("project root must be a directory")
    source_relative = _relative(source_path, "source_path").as_posix()
    if len(test_paths) > 64 or len(support_paths) > 64:
        raise ValueError("selected path list exceeds limit")
    snapshot = _snapshot(root, [source_path, *test_paths, *support_paths], started + max_seconds)
    if source_relative not in snapshot or not source_relative.endswith(".py"):
        raise ValueError("source_path must name a selected Python file")
    try:
        source = snapshot[source_relative].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("source_path must contain UTF-8 Python") from error
    mutants = generate_mutants(source, max_mutants=max_mutants)
    manifest = [{"path": path, "sha256": _digest(data)} for path, data in sorted(snapshot.items())]
    report = {"schema": "parcimonia.mutation-checks/v1", "status": "incomplete",
              "source_path": source_relative, "source_sha256": _digest(snapshot[source_relative]),
              "selected_manifest": manifest, "manifest_sha256": _digest(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")),
              "runner_kind": "command_unittest" if command is not None else "caller_callback",
              "limits": {"max_mutants": max_mutants, "max_executions": max_mutants + 1,
                         "timeout_seconds": timeout_seconds, "max_seconds": max_seconds},
              "baseline": None, "mutations": [],
              "boundaries": {"harness_writes_original_files": False, "security_sandbox": False,
                             "network_isolation": False, "mutation_coverage": "bounded_operator_subset",
                             "callback_deadline": "cooperative"},
              "measurements": {"host_tokens": None, "cost": None}}
    if command is not None:
        # Validate before launching anything, including for no-mutant sources.
        if isinstance(command, (str, bytes)) or not isinstance(command, (list, tuple)) or not 1 <= len(command) <= 64 or not all(isinstance(x, str) and "\x00" not in x and len(x) <= 8192 for x in command) or not command[0]:
            raise ValueError("command must be a nonempty bounded argv without NUL")
        report["command_sha256"] = _digest(json.dumps(list(command), ensure_ascii=False).encode("utf-8"))

    runner_calls = 0

    def execute(replacement: str | None) -> dict:
        nonlocal runner_calls
        remaining = max_seconds - (time.monotonic() - started)
        if remaining <= 0:
            return {"status": "incomplete", "reason": "total_time_budget_exhausted"}
        budget = min(timeout_seconds, remaining)
        with tempfile.TemporaryDirectory(prefix="botte-mutation-") as directory:
            workspace = Path(directory)
            for path, data in snapshot.items():
                destination = workspace / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            if replacement is not None:
                (workspace / source_relative).write_text(replacement, encoding="utf-8")
            call_started = time.monotonic()
            runner_calls += 1
            try:
                result = (run_unittest_command(command, workspace, budget) if command is not None
                          else runner(workspace, budget))
            except Exception as error:
                return {"status": "incomplete", "reason": "runner_exception", "error_type": type(error).__name__}
            if not isinstance(result, dict) or result.get("status") not in ("passed", "failed", "incomplete", "not_run"):
                return {"status": "incomplete", "reason": "invalid_runner_result"}
            # Preserve only JSON evidence; callbacks cannot put arbitrary objects
            # into a report or claim completion after an ignored deadline.
            try:
                serialized = json.dumps(result, allow_nan=False)
                if len(serialized.encode("utf-8")) > 32768:
                    return {"status": "incomplete", "reason": "runner_result_size_limit"}
                result = json.loads(serialized)
            except (TypeError, ValueError, RecursionError):
                return {"status": "incomplete", "reason": "invalid_runner_result"}
            if time.monotonic() - call_started > budget and result["status"] in ("passed", "failed"):
                return {"status": "incomplete", "reason": "attempt_time_budget_exhausted", "observed": result}
            if time.monotonic() - started > max_seconds:
                return {"status": "incomplete", "reason": "total_time_budget_exhausted", "observed": result}
            return result

    baseline = report["baseline"] = execute(None)
    if baseline["status"] != "passed":
        report["status"] = "baseline_failed" if baseline["status"] == "failed" else "baseline_inconclusive"
    else:
        for mutant in mutants:
            if time.monotonic() - started >= max_seconds:
                report["status"] = "budget_exhausted"
                break
            result = execute(mutant["source"])
            outcome = {"failed": "killed", "passed": "survived"}.get(result["status"], "inconclusive")
            report["mutations"].append({"mutation": {k: v for k, v in mutant.items() if k != "source"},
                                        "outcome": outcome, "test_result": result})
        else:
            report["status"] = "completed" if mutants else "no_mutants"
    counts = {outcome: sum(row["outcome"] == outcome for row in report["mutations"])
              for outcome in ("killed", "survived", "inconclusive")}
    report["counts"] = counts
    report["generated_mutants"] = len(mutants)
    report["executions"] = runner_calls
    report["execution_count_basis"] = "runner_calls_including_failed_launch_attempts"
    report["measurements"]["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
    return report
