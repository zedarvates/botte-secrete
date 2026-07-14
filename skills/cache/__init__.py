"""Projet Cache — Évite les re-scans entre agents.

Usage:
    from skills.cache import ProjectCache

    cache = ProjectCache("/home/user/projects/mon-projet")
    scan = cache.get_or_scan()  # Scan if not cached, load if cached

Premier agent (Porthos): scan complet, save cache
Agents suivants: load cache, skip scan → -50% tokens
"""

from __future__ import annotations
from pathlib import Path
import json
import hashlib
import datetime
from typing import Optional, Any
from skills.atomic_json import write_json


class ProjectCache:
    """Cache projet pour éviter les re-scans entre agents.

    Structure:
        .botte-cache/
        ├── project-stats.json    # fichiers, lignes, langages
        ├── scan-result.json      # résultat brut du scanner
        ├── audit-report.json     # dernier audit (si existant)
        ├── fix-report.json       # dernier fix (si existant)
        ├── optimization-plan.json # dernière optimisation (si existant)
        └── skills-profile.json  # .skills-profile copié
    """

    CACHE_DIR_NAME = ".botte-cache"
    MAX_CACHE_AGE_HOURS = 24  # Invalider après 24h
    VERSION = 1  # Incrémenter si le format change
    FINGERPRINT_IGNORES = {
        ".git", ".botte", ".botte-cache", "__pycache__", ".pytest_cache",
    }

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.cache_dir = self.root / self.CACHE_DIR_NAME
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        self.cache_dir.mkdir(exist_ok=True)

    def _key(self, name: str) -> str:
        """Hash du chemin projet pour éviter les collisions."""
        h = hashlib.sha256(str(self.root).encode()).hexdigest()[:8]
        return f"{h}_{name}"

    def _path(self, name: str) -> Path:
        return self.cache_dir / f"{self._key(name)}.json"

    def _project_fingerprint(self) -> str:
        """Cheap metadata fingerprint used to reject stale scan results."""
        digest = hashlib.sha256()
        try:
            files = sorted(
                p for p in self.root.rglob("*")
                if p.is_file()
                and not any(part in self.FINGERPRINT_IGNORES
                            for part in p.relative_to(self.root).parts)
            )
            for path in files:
                stat = path.stat()
                rel = path.relative_to(self.root).as_posix()
                digest.update(f"{rel}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8"))
        except OSError:
            return ""
        return digest.hexdigest()

    def is_fresh(self, name: str) -> bool:
        """Vérifie si le cache existe et est récent."""
        p = self._path(name)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            age = datetime.datetime.now() - datetime.datetime.fromisoformat(data.get("cached_at", "2000-01-01T00:00:00"))
            if age.total_seconds() > self.MAX_CACHE_AGE_HOURS * 3600:
                p.unlink(missing_ok=True)
                return False
            if data.get("version") != self.VERSION:
                p.unlink(missing_ok=True)
                return False
            cached_fingerprint = data.get("project_fingerprint")
            if cached_fingerprint and cached_fingerprint != self._project_fingerprint():
                p.unlink(missing_ok=True)
                return False
            return True
        except (json.JSONDecodeError, KeyError, ValueError):
            p.unlink(missing_ok=True)
            return False

    def get(self, name: str) -> Optional[dict]:
        """Charge depuis le cache. Retourne None si pas de cache ou périmé."""
        fresh = self.is_fresh(name)
        self._log_hit(name, fresh)
        if not fresh:
            return None
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _log_hit(self, name: str, hit: bool) -> None:
        try:
            from skills.events import log_event
            log_event("cache", project_root=self.root, key=name, hit=hit)
        except Exception:
            pass

    def set(self, name: str, data: dict):
        """Sauvegarde dans le cache avec métadonnées."""
        data["cached_at"] = datetime.datetime.now().isoformat()
        data["version"] = self.VERSION
        data["project_root"] = str(self.root)
        data["project_fingerprint"] = self._project_fingerprint()
        write_json(self._path(name), data)

    def get_or_scan(self, scanner_fn) -> dict:
        """Récupère du cache ou scanne si nécessaire.

        Args:
            scanner_fn: callable qui retourne un dict (ex: ProjectScanner().scan())

        Returns:
            dict: résultat du scan (caché ou fresh)
        """
        cached = self.get("scan-result")
        if cached:
            return cached
        result = scanner_fn()
        if isinstance(result, dict):
            self.set("scan-result", result)
        else:
            # Pydantic model → dict
            self.set("scan-result", result.model_dump() if hasattr(result, "model_dump") else dict(result))
        return result

    def get_audit_report(self) -> Optional[dict]:
        return self.get("audit-report")

    def set_audit_report(self, report: dict):
        self.set("audit-report", report)

    def get_fix_report(self) -> Optional[dict]:
        return self.get("fix-report")

    def set_fix_report(self, report: dict):
        self.set("fix-report", report)

    def get_optimization_plan(self) -> Optional[dict]:
        return self.get("optimization-plan")

    def set_optimization_plan(self, plan: dict):
        self.set("optimization-plan", plan)

    def get_skills_profile(self) -> Optional[dict]:
        """Récupère le .skills-profile depuis le cache ou le fichier projet."""
        cached = self.get("skills-profile")
        if cached:
            return cached
        # Fallback: lire le fichier .skills-profile
        sp_path = self.root / ".skills-profile"
        if sp_path.exists():
            data = json.loads(sp_path.read_text(encoding="utf-8"))
            self.set("skills-profile", data)
            return data
        return None

    def invalidate(self, name: Optional[str] = None):
        """Invalide un cache spécifique ou tout le cache.

        Args:
            name: nom du cache à invalider. Si None, invalide tout.
        """
        if name:
            self._path(name).unlink(missing_ok=True)
        else:
            for f in self.cache_dir.glob("*.json"):
                f.unlink(missing_ok=True)

    def stats(self) -> dict:
        """Statistiques du cache."""
        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "files": len(files),
            "size_bytes": total_size,
            "size_kb": total_size // 1024,
            "age": str(datetime.datetime.now() - datetime.datetime.fromtimestamp(
                min(f.stat().st_mtime for f in files) if files else 0
            )),
            "entries": [f.name for f in files],
        }

    def clear_old(self, max_age_hours: int = 168):
        """Nettoie les caches de plus de max_age_hours (défaut: 7 jours)."""
        for f in self.cache_dir.glob("*.json"):
            age = datetime.datetime.now() - datetime.datetime.fromtimestamp(f.stat().st_mtime)
            if age.total_seconds() > max_age_hours * 3600:
                f.unlink(missing_ok=True)


# ── CLI ──

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m skills.cache <project_path> [invalidate|stats|clear]")
        sys.exit(1)

    cache = ProjectCache(sys.argv[1])
    cmd = sys.argv[2] if len(sys.argv) > 2 else "stats"

    if cmd == "stats":
        s = cache.stats()
        print(f"📦 Cache for {sys.argv[1]}")
        print(f"   Files: {s['files']}")
        print(f"   Size:  {s['size_kb']} KB")
        print(f"   Age:   {s['age']}")
        for e in s['entries']:
            print(f"   • {e}")
    elif cmd == "invalidate":
        cache.invalidate()
        print(f"🧹 Cache invalidé pour {sys.argv[1]}")
    elif cmd == "clear":
        cache.clear_old()
        print(f"🧹 Vieux caches nettoyés pour {sys.argv[1]}")
