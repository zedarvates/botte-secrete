"""Codex app-server stdio adapter. No model/provider switch, no automatic approval."""
from __future__ import annotations

import json
import subprocess
import threading
import time

from .state import OCCUPIED


class RpcError(RuntimeError):
    """A received error response, distinct from an ambiguous transport failure."""


class Rpc:
    def __init__(self, command, on_message, on_disconnect, timeout=20):
        self.timeout = timeout
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.pending = {}
        self.lock = threading.RLock()
        self.serial = 0
        self.closed = False
        # argv only. Never run a mission's text through a shell.
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def send(self, message):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise ConnectionError("Codex app-server est déconnecté.")
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

    def call(self, method, params):
        waiter = {"event": threading.Event(), "response": None}
        with self.lock:
            self.serial += 1
            request_id = self.serial
            self.pending[request_id] = waiter
        try:
            self.send({"id": request_id, "method": method, "params": params})
            if not waiter["event"].wait(self.timeout):
                raise TimeoutError("Réponse Codex non reçue ; aucune répétition automatique.")
            response = waiter["response"]
            if response is None:
                raise ConnectionError("Transport interrompu ; exécution à vérifier.")
            if "error" in response:
                raise RpcError(str(response["error"].get("message", "Requête refusée par Codex"))[:1000])
            return response.get("result", {})
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(2 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 2 * 1024 * 1024 or not line.endswith("\n"):
                    raise ValueError("Message app-server hors limite.")
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("Message app-server invalide.")
                if "id" in message and "method" not in message:
                    with self.lock:
                        pending = self.pending.get(message["id"])
                        if pending:
                            pending["response"] = message
                            pending["event"].set()
                else:
                    self.on_message(message)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        finally:
            with self.lock:
                self.closed = True
                for pending in self.pending.values():
                    pending["event"].set()
            self.on_disconnect()

    def close(self):
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()  # Only the process this adapter created.
            self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        self.process.stdout.close()


class CodexEngine:
    mode = "codex"

    def __init__(self, queue, command, timeout=20):
        self.queue = queue
        self.ready = False
        self.note = "Connexion à Codex…"
        self.requests = {}
        self.items = {}
        self.early_completions = {}
        self.closed_turns = {j["turn_id"] for j in self.queue.snapshot()["jobs"]
                             if j["status"] not in OCCUPIED and j["turn_id"]}
        self.lock = threading.RLock()
        self.rpc = Rpc(command, self._message, self._disconnected, timeout)
        try:
            self.rpc.call("initialize", {"clientInfo": {"name": "botte_odin_queue", "title": "Odin Queue", "version": "0.1.0"}})
            self.rpc.send({"method": "initialized", "params": {}})
            self._check_account()
            self.ready = not self.rpc.closed
            self.note = "Codex connecté" if self.ready else "Transport déconnecté"
        except Exception:
            self.rpc.close()
            raise

    def _disconnected(self):
        self.ready = False
        self.note = "Codex déconnecté ; vérifier les anciennes exécutions."
        for job in self.queue.snapshot()["jobs"]:
            if job["status"] in OCCUPIED:
                self.queue.event(job["id"], "unknown", note=self.note)
        self.queue.changed.set()

    def _check_account(self):
        account = self.rpc.call("account/read", {"refreshToken": False})
        if (account.get("account") or {}).get("type") != "chatgpt" or not account.get("requiresOpenaiAuth"):
            raise RpcError("La file nécessite la connexion ChatGPT existante ; aucun fournisseur API n’est lancé.")

    def _message(self, message):
        method = message.get("method")
        params = message.get("params", {})
        turn = params.get("turn", {})
        incoming_turn = params.get("turnId") or turn.get("id")
        if incoming_turn in self.closed_turns:
            if "id" in message and method:
                self.rpc.send({"id": message["id"], "error": {"code": -32602, "message": "Turn is already closed"}})
            return
        job = self.queue.active_for(params.get("threadId"), params.get("turnId") or turn.get("id"))
        if method == "item/started":
            item = params.get("item", {})
            if item.get("type") in {"commandExecution", "fileChange"}:
                with self.lock:
                    self.items[item.get("id")] = item
                    if len(self.items) > 100:
                        self.items.pop(next(iter(self.items)))
        if "id" in message and method:
            if job is None:
                # Never grant an unscoped request.
                self.rpc.send({"id": message["id"], "error": {"code": -32602, "message": "Request is not attached to an active queued turn"}})
                return
            if job["turn_id"] and params.get("turnId") and params["turnId"] != job["turn_id"]:
                self.rpc.send({"id": message["id"], "error": {"code": -32602, "message": "Stale turn"}})
                return
            supported = method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}
            with self.lock:
                request = {"id": message["id"], "method": method, "params": params,
                           "supported": supported, "item": self.items.get(params.get("itemId"), {})}
                self.requests[message["id"]] = (job["id"], request)
            if params.get("turnId") and not job["turn_id"]:
                self.queue.attach(job["id"], turn_id=params["turnId"])
            self.queue.event(job["id"], "approval", request=request)
        elif method == "serverRequest/resolved":
            request_id = params.get("requestId")
            with self.lock:
                saved = self.requests.pop(request_id, None)
            if saved:
                self.queue.event(saved[0], "resolved", request_id=request_id)
        elif method == "turn/completed":
            if job:
                status = turn.get("status")
                if status not in {"completed", "failed", "interrupted"}:
                    self.queue.event(job["id"], "unknown", note="Événement terminal non reconnu.")
                    return
                self.queue.event(job["id"], "complete", status=status,
                                 note="Tour terminé ; résultat à revoir." if status == "completed" else "Tour " + status)
                with self.lock:
                    if turn.get("id"):
                        self.closed_turns.add(turn["id"])
                    self.requests = {key: value for key, value in self.requests.items() if value[0] != job["id"]}
            elif turn.get("id"):
                # Some clients omit threadId and complete before turn/start responds.
                with self.lock:
                    if len(self.early_completions) < 100:
                        self.early_completions[turn["id"]] = message
        elif method == "item/completed" and job:
            item = params.get("item", {})
            if item.get("type") == "agentMessage":
                self.queue.event(job["id"], "message", text=str(item.get("text", "")))

    def start(self, job):
        try:
            self._check_account()
            method = "thread/resume" if job["thread_id"] else "thread/start"
            params = {"cwd": job["cwd"], "sandbox": "readOnly" if job["audit"] else "workspaceWrite"}
            if job["thread_id"]:
                params["threadId"] = job["thread_id"]
            response = self.rpc.call(method, params)
            thread_id = response["thread"]["id"]
            self.queue.attach(job["id"], thread_id=thread_id)
            prompt = ("Mission lancée par la file locale Odin. Respecter les consignes du dépôt et les autorisations existantes. "
                      "Aucune fusion, publication, dépense, intervention matérielle, changement d’accès ou envoi à des tiers "
                      "sans autorisation explicite applicable. Ne pas lancer de sous-agents sans demande applicable. "
                      "Produire les vérifications et les limites du résultat.\n\n" + job["prompt"])
            response = self.rpc.call("turn/start", {"threadId": thread_id, "cwd": job["cwd"],
                                                     "input": [{"type": "text", "text": prompt}]})
            turn_id = response["turn"]["id"]
            self.queue.attach(job["id"], turn_id=turn_id)
            with self.lock:
                early = self.early_completions.pop(turn_id, None)
            if early:
                self._message(early)
        except RpcError as error:
            self.queue.event(job["id"], "complete", status="failed", note=str(error))
        except (OSError, ValueError, KeyError, TypeError, TimeoutError, ConnectionError) as error:
            self.queue.event(job["id"], "unknown", note=str(error)[:1000])

    def cancel(self, job):
        if job["status"] == "cancelling":
            try:
                self.rpc.call("turn/interrupt", {"threadId": job["thread_id"], "turnId": job["turn_id"]})
                # Acknowledgement alone does NOT release the slot. Wait for turn/completed.
            except (RpcError, OSError, TimeoutError, ConnectionError) as error:
                self.queue.event(job["id"], "unknown", note=str(error)[:1000])

    def answer(self, job_id, request_id, decision):
        if decision not in {"accept", "decline"}:
            raise ValueError("Décision invalide ; aucune autorisation de session ajoutée.")
        with self.lock:
            saved = self.requests.get(request_id)
            job = next((j for j in self.queue.snapshot()["jobs"] if j["id"] == job_id), None)
            if (saved is None or saved[0] != job_id or job is None or job["status"] != "waiting_approval"
                    or not saved[1]["supported"]):
                raise ValueError("Demande expirée, non prise en charge ou tour déjà interrompu.")
            available = saved[1]["params"].get("availableDecisions")
            if available is not None and decision not in available:
                raise ValueError("Cette décision n’est pas proposée par Codex.")
            self.rpc.send({"id": request_id, "result": {"decision": decision}})
            # The resolved notification is authoritative; do not free a slot here.

    def tick(self):
        pass

    def close(self):
        self.rpc.close()


class SimulationEngine:
    mode = "simulation"
    ready = True
    note = "Simulation locale : aucun agent ou modèle exécuté"

    def __init__(self, queue, duration=12):
        self.queue = queue
        self.duration = duration
        self.due = {}
        self.lock = threading.RLock()

    def start(self, job):
        self.queue.attach(job["id"], thread_id="demo-" + job["id"], turn_id="demo-turn-" + job["id"])
        with self.lock:
            self.due[job["id"]] = time.monotonic() + self.duration

    def tick(self):
        with self.lock:
            for job_id, deadline in list(self.due.items()):
                if time.monotonic() >= deadline:
                    self.queue.event(job_id, "complete", status="completed", note="Simulation terminée ; aucun effet réel.")
                    self.due.pop(job_id)

    def cancel(self, job):
        with self.lock:
            self.due.pop(job["id"], None)
        if job["status"] == "cancelling":
            self.queue.event(job["id"], "complete", status="interrupted", note="Simulation interrompue.")

    def answer(self, *args):
        raise ValueError("Aucune approbation dans la simulation.")

    def close(self):
        pass
