"""Memory Hub schema - dataclasses, enums, and SQLite DDL."""
from __future__ import annotations
import enum, time
from dataclasses import dataclass, field, asdict
from typing import Any

class MemoryStatus(enum.Enum):
    PROPOSED = "proposal"
    REVIEW_ACTIVE = "review_active"
    PROMOTED = "promoted"
    EXPIRED = "expired"
    OBSOLETED = "obsoleted"
    @classmethod
    def default(cls): return cls.PROPOSED
    def frozen(self): return self in (MemoryStatus.EXPIRED, MemoryStatus.OBSOLETED)
    def allowed_transitions(self): return _STATUS_TRANSITIONS[self]

_STATUS_TRANSITIONS = {
    MemoryStatus.PROPOSED: [MemoryStatus.REVIEW_ACTIVE, MemoryStatus.EXPIRED],
    MemoryStatus.REVIEW_ACTIVE: [MemoryStatus.PROMOTED, MemoryStatus.OBSOLETED],
    MemoryStatus.PROMOTED: [MemoryStatus.OBSOLETED, MemoryStatus.EXPIRED],
    MemoryStatus.EXPIRED: [],
    MemoryStatus.OBSOLETED: [],
}

class MemoryVisibility(enum.Enum):
    PRIVATE = "private"
    PROJECT = "project"
    TEAM = "team"
    RESTRICTED = "restricted"
    @classmethod
    def default(cls): return cls.PRIVATE

class AssetType(enum.Enum):
    CHAT_MEMORY = "chat_memory"; SKILL = "skill"; WIKI = "wiki"
    CODE_GRAPH = "code_graph"; FACT = "fact"; PATTERN = "pattern"; DECISION = "decision"

class MemorySensitivity(enum.IntEnum):
    NONE = 0; LOW = 1; MEDIUM = 3; HIGH = 5

class MemorySourceType(enum.Enum):
    USER = "user"; REPO = "repo"; WEB = "web"; TOOL = "tool"
    AGENT = "agent"; GENERATED = "generated"

class MemoryTrustClass(enum.Enum):
    TRUSTED_USER = "trusted_user"
    EXTERNAL_OBSERVATION = "external_observation"
    GENERATED_UNTRUSTED = "generated_untrusted"

EXTERNAL_SOURCE_TYPES = frozenset({
    MemorySourceType.REPO.value, MemorySourceType.WEB.value,
    MemorySourceType.TOOL.value, MemorySourceType.AGENT.value,
    MemorySourceType.GENERATED.value,
})

@dataclass(slots=True)
class MemoryEntry:
    key: str = ""
    value: Any = None
    asset_type: str = AssetType.FACT.value
    category: str = "fact"
    confidence: float = 1.0
    status: str = MemoryStatus.default().value
    visibility: str = MemoryVisibility.default().value
    sensitivity: int = MemorySensitivity.NONE.value
    project_id: str = "__global__"
    agent_id: str = ""
    source_ref: str = ""
    source_digest: str = ""
    source_type: str = MemorySourceType.USER.value
    source_uri: str = ""
    source_id: str = ""
    run_id: str = "direct"
    observed_at: float = field(default_factory=time.time)
    trust_class: str = MemoryTrustClass.TRUSTED_USER.value
    executable_instruction: bool = False
    quarantined: bool = False
    created_by: str = ""
    expires_at: float | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    version: int = 1
    tags: list[str] = field(default_factory=list)
    def to_dict(self):
        d = asdict(self)
        if self.expires_at is not None: d["expires_at"] = self.expires_at
        return d
    @classmethod
    def from_dict(cls, d):
        kwargs = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**kwargs)

_ENTRY_COLUMNS = """
    key TEXT NOT NULL, value_json TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'fact',
    category TEXT NOT NULL DEFAULT 'fact', confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'proposal', visibility TEXT NOT NULL DEFAULT 'private',
    sensitivity INTEGER NOT NULL DEFAULT 0, project_id TEXT NOT NULL DEFAULT '__global__',
    agent_id TEXT NOT NULL DEFAULT '', source_ref TEXT NOT NULL DEFAULT '',
    source_digest TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT 'generated',
    source_uri TEXT NOT NULL DEFAULT '', source_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT 'legacy', observed_at REAL NOT NULL DEFAULT 0,
    trust_class TEXT NOT NULL DEFAULT 'generated_untrusted',
    executable_instruction INTEGER NOT NULL DEFAULT 0,
    quarantined INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL DEFAULT '',
    expires_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
    tags_json TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (project_id, key)
"""

FULL_DDL = f"""PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS _schema (version INTEGER NOT NULL, applied_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS memory_entries ({_ENTRY_COLUMNS});
CREATE TABLE IF NOT EXISTS memory_quarantine ({_ENTRY_COLUMNS});
CREATE INDEX IF NOT EXISTS idx_memory_project ON memory_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_entries(status);
CREATE INDEX IF NOT EXISTS idx_memory_visibility ON memory_entries(visibility);
CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_entries(expires_at);
CREATE INDEX IF NOT EXISTS idx_memory_asset ON memory_entries(asset_type);
CREATE INDEX IF NOT EXISTS idx_quarantine_project ON memory_quarantine(project_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_source ON memory_quarantine(source_type);
"""

SCHEMA_VERSION = 2
__all__ = ["MemoryStatus", "MemoryVisibility", "AssetType", "MemorySensitivity",
           "MemorySourceType", "MemoryTrustClass", "EXTERNAL_SOURCE_TYPES",
           "MemoryEntry", "FULL_DDL", "SCHEMA_VERSION"]
