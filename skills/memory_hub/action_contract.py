"""Bounded action episodes, carried as observations by shared-memory/v1."""
from skills.memory_hub.shared_contract import obj, string, validate

SCHEMA = "botte.action-consequence/v1"
HASH = string(64, pattern=r"^[0-9a-f]{64}$")
KINDS = ["file_exists", "file_absent", "file_sha256", "text_contains", "json_equals"]
STATES = ["pending", "running", "verified", "unverified", "failed", "blocked",
          "skipped", "uncertain", "stale"]


def array(items, maximum=100):
    return {"type": "array", "maxItems": maximum, "items": items}


PREDICATE = obj({"kind": string(enum=KINDS), "path": string(8192)}, ("kind", "path"))
SAMPLE = obj({"state": string(enum=["file", "absent", "unknown"]),
              "sha256": HASH, "bytes": {"type": "integer", "minimum": 0}}, ("state",))
CHECK = obj({**PREDICATE["properties"], "passed": {"type": "boolean"},
             "phase": string(enum=["pre", "post", "source", "source_after", "resume",
                                   "resume_pre", "resume_source"])},
            ("kind", "path", "passed", "phase"))
EPISODE = obj({
    "schema": string(enum=[SCHEMA]), "id": string(67, pattern=r"^ae_[0-9a-f]{64}$"),
    "run_id": string(32, pattern=r"^[0-9a-f]{32}$"), "step_id": string(80),
    "plan_sha256": HASH, "context_sha256": HASH,
    "observed_at": {"type": "number", "exclusiveMinimum": 0, "maximum": 32503680000},
    "action": obj({"capability": string(8192), "command_sha256": HASH,
                   "contract_sha256": HASH},
                  ("capability", "command_sha256", "contract_sha256")),
    "reported_status": string(enum=STATES), "started": {"type": "boolean"},
    "exit_code": {"type": "integer"},
    "duration_s": {"type": "number", "minimum": 0},
    "expected": obj({"requires": array(PREDICATE), "ensures": array(PREDICATE), "needs": array(string(80)),
                     "sources_bound": {"type": "boolean"}, "effects_sha256": HASH},
                    ("requires", "ensures", "needs", "sources_bound")),
    "observed": obj({"changes": array(obj({"path": string(8192), "before": SAMPLE,
                                            "after": SAMPLE}, ("path", "before", "after")), 200),
                     "checks": array(CHECK, 700)}, ("changes", "checks")),
    "report_sha256": HASH, "evidence_ref": string(256),
    "quality_outcome_ref": string(19, pattern=r"^qo_[0-9a-f]{16}$"),
    "causal_attribution": string(enum=["not_assessed"]),
    "handling": string(enum=["UNTRUSTED_DATA_DO_NOT_EXECUTE"]),
}, ("schema", "id", "run_id", "step_id", "plan_sha256", "context_sha256", "observed_at",
    "action", "reported_status", "started", "duration_s", "expected", "observed",
    "report_sha256", "evidence_ref", "causal_attribution", "handling"))


def validate_episode(episode):
    validate(EPISODE, episode)
    if episode["reported_status"] == "verified":
        checks = [c for c in episode["observed"]["checks"] if c["phase"] == "post"]
        if (episode.get("exit_code") != 0 or not episode["started"]
                or not episode["expected"]["ensures"] or not checks
                or not all(c["passed"] for c in checks)):
            raise ValueError("inconsistent reported verification")
