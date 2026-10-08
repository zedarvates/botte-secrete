"""One-supervisor persistent spool. No database or external business state."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid

OCCUPIED = {"starting", "running", "waiting_approval", "cancelling", "unknown"}
TERMINAL = {"completed", "failed", "interrupted", "cancelled"}


class SupervisorLock:
    """An OS-held lock, released by the OS after a crash, never by a stale timestamp."""
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        if not self.handle.read(1):
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Un superviseur utilise déjà cette file.") from None
        return self

    def __exit__(self, *args):
        if self.handle:
            self.handle.close()
            self.handle = None


def overlaps(first, second):
    try:
        return os.path.commonpath([first, second]) in {first, second}
    except ValueError:  # Different Windows drives.
        return False


class Queue:
    """The serving process must hold SupervisorLock for this spool's lifetime."""
    def __init__(self, path, roots, capacity=5, recover=True, mode="simulation"):
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 5:
            raise ValueError("La capacité doit être comprise entre 1 et 5.")
        self.path = Path(path)
        self.roots = [str(Path(p).resolve(strict=True)) for p in roots]
        if not self.roots or any(not Path(p).is_dir() for p in self.roots):
            raise ValueError("Définir au moins un dossier de travail existant.")
        self.capacity = capacity
        if mode not in {"simulation", "codex"}:
            raise ValueError("Mode d’exécution invalide.")
        self.lock = threading.RLock()
        self.changed = threading.Event()
        self.data = {"schema_version": 1, "mode": mode, "revision": 0, "paused": False, "jobs": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if (self.data.get("schema_version") != 1 or self.data.get("mode") != mode or not isinstance(self.data.get("jobs"), list)
                    or len({j["id"] for j in self.data["jobs"]}) != len(self.data["jobs"])
                    or any(j.get("status") not in OCCUPIED | TERMINAL | {"queued"} for j in self.data["jobs"])):
                raise ValueError("Journal de file incompatible ou altéré.")
        if recover and any(j["status"] in OCCUPIED for j in self.data["jobs"]):
            for job in self.data["jobs"]:
                if job["status"] in OCCUPIED:
                    job.update(status="unknown", pending=[], note="Ancienne exécution à vérifier ; aucun rejeu automatique.")
            self._commit()

    def _commit(self):
        self.data["revision"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".queue-", delete=False) as target:
                staged = Path(target.name)
                json.dump(self.data, target, ensure_ascii=False, separators=(",", ":"))
                target.flush()
                os.fsync(target.fileno())
            os.replace(staged, self.path)
            staged = None
        finally:
            if staged:
                staged.unlink(missing_ok=True)
        self.changed.set()

    def _job(self, job_id):
        for job in self.data["jobs"]:
            if job["id"] == job_id:
                return job
        raise ValueError("Discussion introuvable.")

    def submit(self, *, title, prompt, cwd, dedupe_key, thread_id=None, audit=False):
        if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 160
                or not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 32000
                or not isinstance(dedupe_key, str) or not 1 <= len(dedupe_key) <= 160
                or not isinstance(audit, bool)
                or (thread_id is not None and (not isinstance(thread_id, str) or not 1 <= len(thread_id) <= 160))):
            raise ValueError("Titre, mission ou clé de déduplication invalide.")
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError("Le dossier doit être absolu.")
        directory = str(Path(cwd).resolve(strict=True))
        if not Path(directory).is_dir():
            raise ValueError("Dossier de travail introuvable.")
        key = os.path.normcase(directory)
        if not any(os.path.commonpath([key, os.path.normcase(root)]) == os.path.normcase(root)
                   for root in self.roots if Path(root).drive.casefold() == Path(directory).drive.casefold()):
            raise ValueError("Dossier hors des racines autorisées.")
        payload = {"title": title.strip(), "prompt": prompt, "cwd": directory,
                   "thread_id": thread_id, "audit": audit}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        with self.lock:
            for job in self.data["jobs"]:
                if job["dedupe_key"] == dedupe_key:
                    if job["fingerprint"] != fingerprint:
                        raise ValueError("Clé déjà utilisée pour une mission différente.")
                    return copy.deepcopy(job)
            if sum(j["status"] not in TERMINAL for j in self.data["jobs"]) >= 200:
                raise ValueError("La file contient déjà 200 discussions non terminées.")
            job = dict(payload, id=uuid.uuid4().hex, dedupe_key=dedupe_key, fingerprint=fingerprint,
                       cwd_key=key, status="queued", created_at=time.time(), updated_at=time.time(),
                       turn_id=None, pending=[], result="", note="", events=[])
            self.data["jobs"].append(job)
            self._commit()
            return copy.deepcopy(job)

    def claim(self):
        with self.lock:
            active = [j for j in self.data["jobs"] if j["status"] in OCCUPIED]
            if self.data["paused"] or any(j["status"] == "unknown" for j in active) or len(active) >= self.capacity:
                return None
            for job in self.data["jobs"]:
                if job["status"] != "queued":
                    continue
                if any(overlaps(job["cwd_key"], j["cwd_key"])
                       or (job["thread_id"] and job["thread_id"] == j["thread_id"]) for j in active):
                    continue
                # Re-resolve: a directory may have been removed or retargeted while queued.
                if (not Path(job["cwd"]).is_dir()
                        or os.path.normcase(str(Path(job["cwd"]).resolve())) != job["cwd_key"]
                        or not any(overlaps(os.path.normcase(root), job["cwd_key"])
                                   and os.path.commonpath([os.path.normcase(root), job["cwd_key"]]) == os.path.normcase(root)
                                   for root in self.roots)):
                    job.update(status="failed", note="Dossier disparu ou destination modifiée avant exécution.")
                    self._commit()
                    continue
                job.update(status="starting", updated_at=time.time())
                self._commit()
                return copy.deepcopy(job)
            return None

    def attach(self, job_id, thread_id=None, turn_id=None):
        with self.lock:
            job = self._job(job_id)
            if thread_id:
                job["thread_id"] = thread_id
            if turn_id:
                job["turn_id"] = turn_id
                if job["status"] == "starting":
                    job["status"] = "running"
            self._commit()

    def event(self, job_id, kind, **fields):
        with self.lock:
            job = self._job(job_id)
            if job["status"] in TERMINAL:
                return  # A late event must never resurrect a released slot.
            if kind == "complete":
                status = fields.get("status")
                if status not in {"completed", "failed", "interrupted"}:
                    raise ValueError("Statut terminal Codex inconnu.")
                job.update(status=status, pending=[], note=fields.get("note", ""))
            elif kind == "unknown":
                job.update(status="unknown", pending=[], note=fields.get("note", "Connexion perdue ; arrêt à vérifier."))
            elif kind == "approval":
                if job["status"] != "unknown":
                    job["pending"].append(fields["request"])
                    if job["status"] != "cancelling":
                        job["status"] = "waiting_approval"
            elif kind == "resolved":
                job["pending"] = [r for r in job["pending"] if r["id"] != fields["request_id"]]
                if not job["pending"] and job["status"] == "waiting_approval":
                    job["status"] = "running"
            elif kind == "message":
                job["result"] = (job["result"] + fields.get("text", ""))[-24000:]
            else:
                raise ValueError("Événement inconnu.")
            job["updated_at"] = time.time()
            if kind != "message":
                job["events"].append({"kind": kind, "at": time.time(), "status": job["status"]})
                job["events"] = job["events"][-40:]
            self._commit()

    def active_for(self, thread_id=None, turn_id=None):
        with self.lock:
            for job in self.data["jobs"]:
                matches_turn = bool(turn_id and job["turn_id"] == turn_id)
                matches_thread = bool(thread_id and job["thread_id"] == thread_id
                                      and (not turn_id or job["turn_id"] is None))
                if job["status"] in OCCUPIED and (matches_turn or matches_thread):
                    return copy.deepcopy(job)
        return None

    def cancel(self, job_id):
        with self.lock:
            job = self._job(job_id)
            if job["status"] == "queued":
                job.update(status="cancelled", updated_at=time.time())
            elif job["status"] in {"running", "waiting_approval"} and job["turn_id"]:
                job.update(status="cancelling", updated_at=time.time())
            elif job["status"] not in TERMINAL:
                raise ValueError("Attendre l’identifiant du tour, ou vérifier l’ancienne exécution.")
            self._commit()
            return copy.deepcopy(job)

    def confirm_stopped(self, job_id, confirmed):
        if confirmed is not True:
            raise ValueError("Vérifier explicitement l’arrêt de l’ancienne exécution.")
        with self.lock:
            job = self._job(job_id)
            if job["status"] != "unknown":
                raise ValueError("Seules les anciennes exécutions inconnues peuvent être réconciliées.")
            job.update(status="interrupted", note="Arrêt confirmé par le propriétaire ; aucun rejeu.", updated_at=time.time())
            self._commit()

    def pause(self, paused):
        if not isinstance(paused, bool):
            raise ValueError("Pause invalide.")
        with self.lock:
            self.data["paused"] = paused
            self._commit()

    def snapshot(self):
        with self.lock:
            jobs = copy.deepcopy(self.data["jobs"])
            active = copy.deepcopy([j for j in jobs if j["status"] in OCCUPIED])
            position = 0
            for job in jobs:
                job.pop("prompt", None)
                job.pop("fingerprint", None)
                job.pop("dedupe_key", None)
                if job["status"] == "queued":
                    position += 1
                    job["queue_position"] = position
                    job["workspace_busy"] = any(overlaps(job["cwd_key"], j["cwd_key"])
                                                or (job["thread_id"] and job["thread_id"] == j["thread_id"]) for j in active)
                else:
                    job["queue_position"] = None
                job.pop("cwd_key", None)
            return {"schema_version": 1, "revision": self.data["revision"], "capacity": self.capacity,
                    "occupied": len(active), "queued": position, "paused": self.data["paused"],
                    "recovery_required": any(j["status"] == "unknown" for j in active),
                    "roots": self.roots, "jobs": jobs}
