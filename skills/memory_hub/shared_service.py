"""Authenticated service layer over the existing MemoryStore v2.

One service call opens its own connection. BEGIN IMMEDIATE serializes version
checks, entry changes, history and idempotency receipts across processes.
Legacy MCP functions remain local APIs; the network facade never dispatches them.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from skills.context_budget.budget import Item, knapsack
from skills.memory_hub.schema import MemoryEntry, MemoryStatus
from skills.memory_hub.shared_contract import (
    CONTRACT_VERSION, IDENTIFIER, MAX_BODY, PROJECT, READ_ONLY, SCHEMAS, encode, validate,
)
from skills.memory_hub.scribe import advise, rank
from skills.memory_hub.store import MemoryStore

_DDL = """
CREATE TABLE IF NOT EXISTS shared_revisions (
    key TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL,
    recorded_at REAL NOT NULL, PRIMARY KEY (key, version));
CREATE TABLE IF NOT EXISTS shared_requests (
    actor TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
    key TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY (actor, request_id));
CREATE TABLE IF NOT EXISTS shared_vectors (
    key TEXT PRIMARY KEY, embedding TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shared_tombstones (
    key_digest TEXT PRIMARY KEY, forgotten_at REAL NOT NULL);
"""
RIGHTS = frozenset({"read", "write", "review", "forget", "curate", "user_ingress"})
MAX_POOL = 2000


class ServiceError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class Principal:
    actor_id: str
    projects: frozenset[str]
    rights: frozenset[str]

    def __post_init__(self):
        validate(IDENTIFIER, self.actor_id, "principal.actor_id")
        if not self.projects or not self.rights or not self.rights <= RIGHTS:
            raise ValueError("principal requires explicit projects and known rights")
        for project in self.projects:
            validate(PROJECT, project, "principal.projects")


def _digest(data):
    return hashlib.sha256(encode(data)).hexdigest()


def _require(condition, message="Operation is not allowed"):
    if not condition:
        raise ServiceError("forbidden", message, 403)


def _can_read(entry, principal):
    return entry.agent_id == principal.actor_id or entry.visibility in {"project", "team"}


def _can_write(entry, principal):
    return entry.agent_id == principal.actor_id or "curate" in principal.rights


def _text(entry):
    if isinstance(entry.value, dict) and isinstance(entry.value.get("text"), str):
        return entry.value["text"]
    return json.dumps(entry.value, ensure_ascii=False)


class MemoryService:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)

    def call(self, operation, args, principal):
        if operation not in SCHEMAS:
            raise ServiceError("unknown_operation", "Unknown memory operation", 404)
        try:
            validate(SCHEMAS[operation], args)
            if len(encode(args)) > MAX_BODY:
                raise ServiceError("too_large", "Request too large", 413)
        except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError) as error:
            raise ServiceError("invalid_input", str(error)) from error
        _require(args["project_id"] in principal.projects, "Project is outside this identity's scope")
        right = "read" if operation in READ_ONLY else (
            "review" if operation == "review" else "forget" if operation == "forget" else "write")
        _require(right in principal.rights)
        with MemoryStore(self.base_dir) as store:
            conn = store._conn(args["project_id"])
            conn.executescript(_DDL)
            if operation in READ_ONLY:
                # A read transaction keeps a recall/wiki/history result on one snapshot.
                conn.execute("BEGIN")
                try:
                    return self._read(operation, args, principal, store, conn)
                finally:
                    conn.rollback()
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                return self._write(operation, args, principal, store, conn)

    @staticmethod
    def _entry(store, conn, args):
        row, _ = store._get_raw(conn, args["project_id"], args["key"])
        return store._row_to_entry(row) if row else None

    def _write(self, operation, args, principal, store, conn):
        key, project = args["key"], args["project_id"]
        key_digest = _digest([project, key])
        if conn.execute("SELECT 1 FROM shared_tombstones WHERE key_digest = ?",
                        (key_digest,)).fetchone():
            raise ServiceError("forgotten", "This key was forgotten; use a new key for new consent", 409)
        fingerprint = _digest([operation, args])
        receipt = conn.execute("SELECT fingerprint, response FROM shared_requests "
                               "WHERE actor = ? AND request_id = ?",
                               (principal.actor_id, args["request_id"])).fetchone()
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise ServiceError("request_conflict", "request_id already refers to different input", 409)
            return {**json.loads(receipt["response"]), "replayed": True}

        entry = self._entry(store, conn, args)
        if operation in {"capture", "checkpoint"}:
            if entry:
                # Do not reveal someone else's private record through existence checks.
                _require(_can_write(entry, principal))
                raise ServiceError("key_exists", "Use correct with the current version", 409)
        else:
            if not entry:
                raise ServiceError("not_found", "Memory not found", 404)
            _require(_can_read(entry, principal))
            if operation != "review":
                _require(_can_write(entry, principal))
            if entry.version != args["expected_version"]:
                raise ServiceError("version_conflict", "Memory changed; read its current version", 409)

        if operation == "forget":
            for table in ("memory_entries", "memory_quarantine", "shared_revisions",
                          "shared_vectors", "shared_requests"):
                conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
            conn.execute("INSERT INTO shared_tombstones VALUES (?, ?)", (key_digest, time.time()))
            return {"schema": CONTRACT_VERSION, "key": key, "deleted": True,
                    "scope": "live_store_revisions_vectors_receipts",
                    "external_copies_deleted": False, "tombstone_retained": True}

        if entry:
            self._snapshot(conn, entry)
        if operation == "review":
            target = MemoryStatus(args["new_status"])
            if target not in MemoryStatus(entry.status).allowed_transitions():
                raise ServiceError("transition_conflict", "Lifecycle transition is not allowed", 409)
            if entry.quarantined and target is MemoryStatus.PROMOTED:
                raise ServiceError("quarantine", "External observations cannot be promoted", 403)
            entry.status = target.value
        else:
            if operation == "checkpoint" and args["record"]["kind"] != "checkpoint":
                raise ServiceError("invalid_input", "checkpoint requires kind=checkpoint")
            entry = self._build_entry(args, principal, entry)
        store.store(entry, commit=False)
        entry = self._entry(store, conn, args)
        if operation != "review":
            conn.execute("DELETE FROM shared_vectors WHERE key = ?", (key,))
            if "embedding" in args["record"]:
                conn.execute("INSERT INTO shared_vectors VALUES (?, ?)",
                             (key, encode(args["record"]["embedding"]).decode("utf-8")))
        self._snapshot(conn, entry)
        response = {"schema": CONTRACT_VERSION, "project_id": project, "key": key,
                    "version": entry.version, "status": entry.status,
                    "quarantined": entry.quarantined, "executable_instruction": False,
                    "replayed": False}
        conn.execute("INSERT INTO shared_requests VALUES (?, ?, ?, ?, ?)",
                     (principal.actor_id, args["request_id"], fingerprint, key,
                      encode(response).decode("utf-8")))
        return response

    @staticmethod
    def _snapshot(conn, entry):
        conn.execute("INSERT OR IGNORE INTO shared_revisions VALUES (?, ?, ?, ?)",
                     (entry.key, entry.version, encode(entry.to_dict()).decode("utf-8"), time.time()))

    @staticmethod
    def _build_entry(args, principal, previous):
        record, now = args["record"], time.time()
        source = record["source"]
        if source["type"] == "user":
            _require("user_ingress" in principal.rights,
                     "Only a configured user ingress can identify a trusted-user source")
        if source["observed_at"] > now + 300:
            raise ServiceError("invalid_input", "Observation timestamp is in the future")
        expires = record.get("expires_at")
        if expires is not None and expires <= source["observed_at"]:
            raise ServiceError("invalid_input", "Expiry must follow the observation")
        if "embedding" in record and not any(record["embedding"]["vector"]):
            raise ServiceError("invalid_input", "Embedding must have a nonzero norm")
        value = {"text": record["text"], "source_excerpt": source["excerpt"],
                 "evidence_refs": record.get("evidence_refs", []),
                 "subject_ref": record.get("subject_ref", ""),
                 "evidence_verified": False}
        trusted = source["type"] == "user"
        if previous is not None and previous.quarantined and trusted:
            raise ServiceError("quarantine", "A correction cannot relabel an external source as trusted", 403)
        return MemoryEntry(
            key=args["key"], value=value, category=record["kind"],
            asset_type={"decision": "decision", "procedure": "skill"}.get(record["kind"], "fact"),
            project_id=args["project_id"], agent_id=previous.agent_id if previous else principal.actor_id,
            created_by=previous.created_by if previous else principal.actor_id,
            source_type=source["type"], source_id=source["id"], source_uri=source.get("uri", ""),
            source_ref=source.get("uri", source["id"]), run_id=source["run_id"],
            source_digest=hashlib.sha256(source["excerpt"].encode("utf-8")).hexdigest(),
            observed_at=source["observed_at"], trust_class="trusted_user" if trusted else "external_observation",
            quarantined=not trusted, executable_instruction=False, confidence=0.0,
            status="proposal", visibility=record.get("visibility", previous.visibility if previous else "private"),
            sensitivity=previous.sensitivity if previous else 0, expires_at=expires,
            tags=record.get("tags", []))

    @staticmethod
    def _candidates(args, principal, store, conn, area="context"):
        table = "memory_entries" if area == "context" else "memory_quarantine"
        filters = ("status = 'promoted' AND quarantined = 0 AND source_type = 'user' "
                   "AND trust_class = 'trusted_user'" if area == "context" else
                   "status NOT IN ('expired', 'obsoleted') AND quarantined = 1")
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE project_id = ? AND {filters} "
            "AND (expires_at IS NULL OR expires_at > ?) "
            "AND (visibility IN ('project', 'team') OR agent_id = ?) "
            "ORDER BY updated_at DESC, key ASC LIMIT ?",
            (args["project_id"], time.time(), principal.actor_id, MAX_POOL + 1)).fetchall()
        candidates = []
        for row in rows[:MAX_POOL]:
            entry = store._row_to_entry(row)
            vector = conn.execute("SELECT embedding FROM shared_vectors WHERE key = ?",
                                  (entry.key,)).fetchone()
            value = entry.value if isinstance(entry.value, dict) else {}
            refs = value.get("evidence_refs", [])
            if not isinstance(refs, list):
                refs = []
            tags = entry.tags if isinstance(entry.tags, list) else []
            candidates.append({"entry": entry, "text": _text(entry),
                               "search_text": " ".join([_text(entry), str(value.get("subject_ref", "")),
                                                        *[str(x) for x in tags + refs]]),
                               "embedding": json.loads(vector[0]) if vector else None})
        return candidates, len(rows) > MAX_POOL

    def _read(self, operation, args, principal, store, conn):
        if operation == "history":
            entry = self._entry(store, conn, args)
            if not entry:
                raise ServiceError("not_found", "Memory not found", 404)
            _require(_can_read(entry, principal) and _can_write(entry, principal))
            rows = conn.execute("SELECT snapshot FROM shared_revisions WHERE key = ? "
                                "ORDER BY version DESC LIMIT 21", (entry.key,)).fetchall()
            response = {"schema": CONTRACT_VERSION, "key": entry.key,
                    "revisions": [json.loads(row[0]) for row in rows[:20]],
                    "truncated": len(rows) > 20, "handling": "DATA_DO_NOT_EXECUTE"}
            while len(encode(response)) > 65_536:
                response["revisions"].pop()
                response["truncated"] = True
            return response

        area = args.get("area", "context") if operation == "recall" else "context"
        candidates, truncated = self._candidates(args, principal, store, conn, area)
        if operation == "scribe":
            return {"schema": CONTRACT_VERSION, **advise(args["record"], candidates),
                    "candidate_pool_truncated": truncated}
        ranked = rank(args.get("query", ""), candidates, args.get("embedding"))[:100]
        views = [self._view(item, area) for item in ranked]
        limit, budget = args.get("limit", 10), args.get("max_bytes", 16_384)
        views = views[:limit]
        items = [Item(v["key"], "doc", len(encode(v)) + 1, ranked[i]["score"])
                 for i, v in enumerate(views)]
        selected, _, _ = knapsack(items, budget - 768, unit=32)
        response = {"schema": CONTRACT_VERSION, "project_id": args["project_id"],
                    "area": area, "entries": [views[i] for i in selected],
                    "candidate_pool_truncated": truncated,
                    "omitted_for_budget": len(views) - len(selected),
                    "retrieval": "lexical_cosine_rrf" if "embedding" not in args else "hybrid_cosine_rrf",
                    "budget_unit": "utf8_bytes", "data_only": True}
        if operation == "wiki":
            response = {"schema": CONTRACT_VERSION, "project_id": args["project_id"],
                        "markdown": self._markdown(args["project_id"], response["entries"]),
                        "generated_at": time.time(), "current_view": True,
                        "candidate_pool_truncated": truncated,
                        "omitted_for_budget": response["omitted_for_budget"]}
        # Enforce the actual serialized byte bound, including metadata/Markdown escaping.
        while len(encode(response)) > budget:
            if operation == "wiki":
                if not selected:
                    raise ServiceError("budget", "Metadata exceeds the requested budget")
                selected.pop()
                response["markdown"] = self._markdown(args["project_id"], [views[i] for i in selected])
            elif response["entries"]:
                response["entries"].pop()
            else:
                raise ServiceError("budget", "Metadata exceeds the requested budget")
            response["omitted_for_budget"] += 1
        return response

    @staticmethod
    def _view(candidate, area):
        entry = candidate["entry"]
        return {"key": entry.key, "version": entry.version, "kind": entry.category,
                "text": candidate["text"], "status": entry.status,
                "handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE" if area == "observations" else "DATA_DO_NOT_EXECUTE",
                "provenance": {"source_type": entry.source_type, "source_id": entry.source_id,
                               "source_uri": entry.source_uri, "source_digest": entry.source_digest,
                               "run_id": entry.run_id, "observed_at": entry.observed_at,
                               "recorded_at": entry.updated_at, "trust_class": entry.trust_class},
                "expires_at": entry.expires_at, "similarities": candidate["channels"],
                "evidence": entry.value.get("evidence_refs", []) if isinstance(entry.value, dict) else [],
                "subject_ref": entry.value.get("subject_ref", "") if isinstance(entry.value, dict) else "",
                "executable_instruction": False}

    @staticmethod
    def _markdown(project, entries):
        # Escape Markdown and HTML from remembered content, including wiki links.
        def literal(value):
            return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(str(value)))

        lines = [f"# Mémoire — {project}", "", "Vue générée à partir des souvenirs relus. Les sources restent la référence.", ""]
        for entry in entries:
            source = entry["provenance"]
            observed = datetime.fromtimestamp(source["observed_at"], timezone.utc).isoformat()
            lines.extend([f"## {entry['key']} · v{entry['version']}", "",
                          f"Type : {literal(entry['kind'])} · Statut : {literal(entry['status'])}", "",
                          *["> " + literal(line) for line in entry["text"].splitlines()], "",
                          "Source : " + literal(source["source_uri"] or source["source_id"]),
                          "", "Observation UTC : " + observed,
                          "", "Référence concernée : " + literal(entry["subject_ref"] or "non précisée"),
                          "", "Empreinte de l’extrait conservé : " + literal(source["source_digest"]), ""])
        return "\n".join(lines)
