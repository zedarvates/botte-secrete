"""Loopback-only UI and admission loop. Python 3.10+, standard library."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import threading
from urllib.parse import urlsplit

from .codex import CodexEngine, SimulationEngine
from .state import Queue, SupervisorLock

ASSETS = Path(__file__).parent


class Service:
    def __init__(self, queue, engine):
        self.queue = queue
        self.engine = engine
        self.stop = threading.Event()
        self.failure = None
        self.thread = threading.Thread(target=self._dispatch, daemon=True)

    def _dispatch(self):
        try:
            while not self.stop.is_set():
                self.queue.changed.clear()
                self.engine.tick()
                if self.engine.ready:
                    while not self.stop.is_set():
                        job = self.queue.claim()
                        if not job:
                            break
                        threading.Thread(target=self.engine.start, args=(job,), daemon=True).start()
                self.queue.changed.wait(0.3)
        except Exception as error:
            # A persistence/admission failure halts all new starts.
            self.failure = type(error).__name__
            self.stop.set()

    def snapshot(self):
        result = self.queue.snapshot()
        result.update(mode=self.engine.mode, connected=self.engine.ready,
                      engine_note=self.engine.note, supervisor_error=self.failure)
        return result

    def close(self):
        self.stop.set()
        self.queue.changed.set()
        self.thread.join(timeout=2)
        self.engine.close()


def make_http(service, port=8775, token=None):
    token = token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No prompts, paths or bearer tokens in access logs.

        def _trusted(self, api=False):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                self._json(403, {"error": "Hôte non autorisé."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + host:
                self._json(403, {"error": "Origine non autorisée."})
                return False
            if api and not secrets.compare_digest(self.headers.get("Authorization", "").encode("utf-8"), ("Bearer " + token).encode("utf-8")):
                self._json(401, {"error": "Ouvrir le lien fourni par le superviseur local."})
                return False
            return True

        def _reply(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, value):
            self._reply(code, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self._trusted(api=path.startswith("/api/")):
                return
            if path == "/api/state":
                self._json(200, service.snapshot())
                return
            names = {"/": ("ui.html", "text/html"), "/ui.js": ("ui.js", "text/javascript"),
                     "/ui.css": ("ui.css", "text/css")}
            if path not in names:
                self._json(404, {"error": "Route introuvable."})
                return
            name, mime = names[path]
            self._reply(200, (ASSETS / name).read_bytes(), mime + "; charset=utf-8")

        def do_POST(self):
            if not self._trusted(api=True):
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Un corps JSON est requis.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 128000:
                    raise ValueError("Requête hors limite.")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Objet JSON requis.")
                path = urlsplit(self.path).path
                if path == "/api/jobs":
                    job = service.queue.submit(title=data.get("title"), prompt=data.get("prompt"),
                                               cwd=data.get("cwd"), dedupe_key=data.get("dedupe_key"),
                                               thread_id=data.get("thread_id") or None, audit=data.get("audit", False))
                    self._json(200, {"id": job["id"]})
                elif path == "/api/control":
                    service.queue.pause(data.get("paused"))
                    self._json(200, {"ok": True})
                elif path == "/api/demo":
                    if service.engine.mode != "simulation":
                        raise ValueError("La démonstration est réservée à la simulation.")
                    batch = data.get("dedupe_key")
                    if not isinstance(batch, str) or not 1 <= len(batch) <= 80:
                        raise ValueError("Clé de démonstration invalide.")
                    for number in range(1, 9):
                        folder = Path(service.queue.roots[0]) / ("demo-" + str(number))
                        folder.mkdir(exist_ok=True)
                        service.queue.submit(title=f"Discussion {number}", prompt="Simulation uniquement.",
                                             cwd=str(folder), dedupe_key=batch + "-" + str(number))
                    self._json(200, {"ok": True})
                else:
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[:2] != ["api", "jobs"]:
                        self._json(404, {"error": "Route introuvable."})
                        return
                    job_id, action = parts[2:]
                    if action == "cancel":
                        service.engine.cancel(service.queue.cancel(job_id))
                    elif action == "approval":
                        service.engine.answer(job_id, data.get("request_id"), data.get("decision"))
                    elif action == "resolve":
                        service.queue.confirm_stopped(job_id, data.get("stopped_confirmed"))
                    else:
                        raise ValueError("Action inconnue.")
                    self._json(200, {"ok": True})
            except (ValueError, OSError, TypeError, KeyError) as error:
                self._json(400, {"error": str(error)[:1000]})
            except Exception:
                self._json(503, {"error": "Opération interrompue ; aucun départ supplémentaire autorisé."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, token


def main(argv=None):
    parser = argparse.ArgumentParser(description="File locale Codex, cinq exécutions maximum et badges dynamiques.")
    parser.add_argument("--live", action="store_true", help="Lancer le Codex déjà installé, avec ses accès existants")
    parser.add_argument("--root", action="append", help="Dossier de travail autorisé, répétable ; obligatoire en mode réel")
    parser.add_argument("--state", type=Path, help="Journal privé de cette file ; pas un registre métier Kanboard")
    parser.add_argument("--port", type=int, default=8775)
    parser.add_argument("--max-running", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--codex-executable", help="Chemin de l’exécutable Codex installé")
    parser.add_argument("--demo-duration", type=float, default=12)
    args = parser.parse_args(argv)
    mode = "codex" if args.live else "simulation"
    if args.live and not args.root:
        parser.error("Définir au moins une racine avec --root ; aucun accès global implicite.")
    if args.demo_duration <= 0 or args.demo_duration > 3600:
        parser.error("Durée de démonstration invalide.")
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")) / "botte-secrete" / "odin-queue"
    path = args.state or base / ("queue-" + mode + ".json")
    roots = args.root
    if not roots:
        demo_root = base / "simulation-workspaces"
        demo_root.mkdir(parents=True, exist_ok=True)
        roots = [str(demo_root)]
    try:
        with SupervisorLock(str(path) + ".lock"):
            queue = Queue(path, roots, capacity=args.max_running, mode=mode)
            if args.live:
                executable = args.codex_executable or shutil.which("codex")
                if not executable:
                    raise ValueError("Codex CLI introuvable ; aucune installation ou connexion de compte automatique.")
                if Path(executable).suffix.lower() in {".cmd", ".bat"}:
                    raise ValueError("Utiliser le véritable codex.exe installé, pas un wrapper shell .cmd/.bat.")
                engine = CodexEngine(queue, [executable, "app-server"])
            else:
                engine = SimulationEngine(queue, args.demo_duration)
            service = Service(queue, engine)
            try:
                server, token = make_http(service, args.port)
            except Exception:
                engine.close()
                raise
            service.thread.start()
            print(json.dumps({"mode": mode, "max_running": queue.capacity, "url": f"http://127.0.0.1:{server.server_port}/#token={token}"}), flush=True)
            try:
                server.serve_forever(poll_interval=0.3)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
                service.close()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"error": str(error)[:1000]}, ensure_ascii=True), file=sys.stderr)
        return 1
