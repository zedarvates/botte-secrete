"""Expiring, recoverable Git worktree leases for isolated workers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skills.atomic_json import write_json


LEASE_SCHEMA = "botte.workspace-lease/v1"
LEASE_STATES = ("ACTIVE", "RELEASED", "QUARANTINED", "EXPIRED")


class WorkspaceLeaseError(RuntimeError):
    """A worktree lease could not be created, inspected or released safely."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git(root: Path, *args: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceLeaseError(f"git {' '.join(args)} failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:500]
        raise WorkspaceLeaseError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _safe_worker(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 64:
        raise WorkspaceLeaseError("worker_id must contain 1-64 characters")
    if any(not (ch.isalnum() or ch in "._-") for ch in cleaned):
        raise WorkspaceLeaseError("worker_id contains unsupported characters")
    return cleaned


def _safe_lease_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith("wl_") or len(cleaned) != 19:
        raise WorkspaceLeaseError("lease_id has an invalid shape")
    if any(char not in "0123456789abcdef" for char in cleaned[3:]):
        raise WorkspaceLeaseError("lease_id has an invalid shape")
    return cleaned


class _RepoLock:
    """Small cross-platform exclusive lock using O_EXCL.

    Git also locks its worktree metadata. This outer lock prevents our registry
    and Git operations from interleaving across local worker processes.
    """

    def __init__(self, path: Path, timeout: float = 30.0) -> None:
        self.path = path
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.write(self.fd, f"{os.getpid()}\n".encode("ascii"))
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise WorkspaceLeaseError(
                        f"timed out waiting for repository lease lock: {self.path}"
                    )
                time.sleep(0.02)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@dataclass
class WorkspaceLease:
    schema: str
    lease_id: str
    worker_id: str
    repo_root: str
    workspace_path: str
    base_sha: str
    head_sha: str
    created_at: str
    expires_at: str
    state: str
    dirty_tree_sha256: str
    workspace_fingerprint: str

    def contract_view(self) -> dict:
        """Return the privacy-safe lease fields allowed in handoffs."""
        return {
            "lease_id": self.lease_id,
            "worker_id": self.worker_id,
            "state": self.state,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "expires_at": self.expires_at,
            "workspace_fingerprint": self.workspace_fingerprint,
        }


class WorktreeLeaseManager:
    """Create and track one recoverable Git worktree per worker run."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        workspace_root: str | Path | None = None,
    ) -> None:
        requested = Path(repo_root).resolve()
        top = _git(requested, "rev-parse", "--show-toplevel")
        self.repo_root = Path(top).resolve()
        common = Path(_git(self.repo_root, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = (self.repo_root / common).resolve()
        self.common_git_dir = common
        self.lock_path = self.common_git_dir / "botte-worktree-lease.lock"
        self.registry_dir = self.repo_root / ".botte-cache" / "workspace-leases"
        self.workspace_root = (
            Path(workspace_root).resolve()
            if workspace_root is not None
            else self.repo_root.parent / f".{self.repo_root.name}-botte-worktrees"
        )

    def _record_path(self, lease_id: str) -> Path:
        return self.registry_dir / f"{_safe_lease_id(lease_id)}.json"

    def _save(self, lease: WorkspaceLease) -> None:
        write_json(self._record_path(lease.lease_id), asdict(lease))

    def create(
        self,
        worker_id: str,
        *,
        base_ref: str = "HEAD",
        ttl_seconds: int = 3600,
    ) -> WorkspaceLease:
        """Create a detached worktree and persist an expiring local lease."""
        worker = _safe_worker(worker_id)
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise WorkspaceLeaseError("ttl_seconds must be a positive integer")
        base_sha = _git(self.repo_root, "rev-parse", f"{base_ref}^{{commit}}")
        created = _utc_now()
        lease_id = "wl_" + uuid.uuid4().hex[:16]
        workspace = self.workspace_root / f"{worker}-{lease_id}"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        with _RepoLock(self.lock_path):
            if workspace.exists():
                raise WorkspaceLeaseError(f"workspace already exists: {workspace}")
            try:
                _git(
                    self.repo_root,
                    "worktree",
                    "add",
                    "--detach",
                    str(workspace),
                    base_sha,
                    timeout=120,
                )
            except BaseException:
                try:
                    workspace.rmdir()
                except OSError:
                    pass
                raise

            lease = WorkspaceLease(
                schema=LEASE_SCHEMA,
                lease_id=lease_id,
                worker_id=worker,
                repo_root=str(self.repo_root),
                workspace_path=str(workspace),
                base_sha=base_sha,
                head_sha=base_sha,
                created_at=created.isoformat(),
                expires_at=(created + timedelta(seconds=ttl_seconds)).isoformat(),
                state="ACTIVE",
                dirty_tree_sha256="",
                workspace_fingerprint="",
            )
            lease = self.refresh(lease, persist=False)
            self._save(lease)
            return lease

    def load(self, lease_id: str) -> WorkspaceLease:
        path = self._record_path(lease_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            lease = WorkspaceLease(**payload)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise WorkspaceLeaseError(f"cannot load workspace lease {lease_id}") from exc
        if lease.schema != LEASE_SCHEMA or lease.state not in LEASE_STATES:
            raise WorkspaceLeaseError(f"invalid workspace lease record: {lease_id}")
        if Path(lease.repo_root).resolve() != self.repo_root:
            raise WorkspaceLeaseError("workspace lease belongs to another repository")
        return lease

    def refresh(
        self,
        lease: WorkspaceLease | str,
        *,
        persist: bool = True,
    ) -> WorkspaceLease:
        """Refresh head/dirty fingerprints and mark elapsed active leases expired."""
        current = self.load(lease) if isinstance(lease, str) else lease
        workspace = Path(current.workspace_path)
        if current.state in ("ACTIVE", "QUARANTINED") and workspace.is_dir():
            current.head_sha = _git(workspace, "rev-parse", "HEAD")
            raw_status = _git(workspace, "status", "--porcelain=v1", "-z")
            current.dirty_tree_sha256 = hashlib.sha256(
                raw_status.encode("utf-8")
            ).hexdigest()
            basis = json.dumps(
                {
                    "lease_id": current.lease_id,
                    "worker_id": current.worker_id,
                    "base_sha": current.base_sha,
                    "head_sha": current.head_sha,
                    "dirty_tree_sha256": current.dirty_tree_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            current.workspace_fingerprint = hashlib.sha256(
                basis.encode("utf-8")
            ).hexdigest()
            expiry = datetime.fromisoformat(current.expires_at.replace("Z", "+00:00"))
            if current.state == "ACTIVE" and _utc_now() >= expiry:
                current.state = "EXPIRED"
        elif current.state == "ACTIVE":
            current.state = "EXPIRED"
        if persist:
            self._save(current)
        return current

    def list(self) -> list[WorkspaceLease]:
        records = []
        if not self.registry_dir.exists():
            return records
        for path in sorted(self.registry_dir.glob("wl_*.json")):
            try:
                records.append(self.refresh(path.stem))
            except WorkspaceLeaseError:
                continue
        return records

    def quarantine(self, lease: WorkspaceLease | str) -> WorkspaceLease:
        current = self.load(lease) if isinstance(lease, str) else lease
        current.state = "QUARANTINED"
        current = self.refresh(current, persist=False)
        self._save(current)
        return current

    def release(self, lease: WorkspaceLease | str) -> WorkspaceLease:
        """Remove only a clean worktree; dirty state is preserved in quarantine."""
        current = self.load(lease) if isinstance(lease, str) else lease
        current = self.refresh(current)
        workspace = Path(current.workspace_path)
        if current.state == "RELEASED":
            return current
        if not workspace.exists():
            current.state = "RELEASED"
            self._save(current)
            return current

        raw_status = _git(workspace, "status", "--porcelain=v1", "-z")
        if raw_status:
            current.state = "QUARANTINED"
            self._save(current)
            return current

        with _RepoLock(self.lock_path):
            _git(
                self.repo_root,
                "worktree",
                "remove",
                str(workspace),
                timeout=120,
            )
            current.state = "RELEASED"
            self._save(current)
        return current


__all__ = [
    "LEASE_SCHEMA",
    "LEASE_STATES",
    "WorkspaceLease",
    "WorkspaceLeaseError",
    "WorktreeLeaseManager",
]
