"""Botte Secrète — Local LLM MCP server (stdio, JSON-RPC 2.0, stdlib only).

Exposes the llm_backends capabilities as Model Context Protocol tools so any MCP
client (Claude Code, Cursor, etc.) can:

    discover_backends   scan localhost/network for LM Studio, Ollama, …
    list_models         list models the registered backends expose
    audit_local_usage   are local models used? + hardware-aware setup advice
    route_task          recommend a tier/backend for a task (cost-aware)
    local_chat          run a prompt on a local model  ← offloads cloud tokens

Implements the minimal MCP handshake: initialize → tools/list → tools/call.
Newline-delimited JSON-RPC over stdin/stdout. No third-party dependencies.

Register in Claude Code (.mcp.json or settings):
    {
      "mcpServers": {
        "botte-llm": {
          "command": "python",
          "args": ["-m", "skills.llm_mcp.server"],
          "cwd": "/path/to/botte-secrete"
        }
      }
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the repo importable whether launched as `-m` or as a bare script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.llm_backends import registry  # noqa: E402
from skills.llm_backends.audit import audit  # noqa: E402
from skills.llm_backends.client import LocalLLMClient, LocalLLMError  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "botte-llm", "version": "1.0.0"}

# ── Tool definitions (MCP inputSchema = JSON Schema) ─────────────────────────

TOOLS = [
    {
        "name": "discover_backends",
        "description": "Scan for local LLM servers (LM Studio, Ollama, LocalAI, "
                       "vLLM, llama.cpp, ComfyUI, Qdrant) on localhost or the "
                       "network, and register what is reachable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hosts": {"type": "array", "items": {"type": "string"},
                          "description": "Explicit hosts/IPs to probe. Default: 127.0.0.1."},
                "scan_subnet": {"type": "boolean",
                                "description": "Also sweep the local /24 network."},
            },
        },
    },
    {
        "name": "list_models",
        "description": "List the models exposed by registered local backends.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "audit_local_usage",
        "description": "Report whether local models are in use, profile the host "
                       "hardware (RAM/VRAM/GPU), and give hardware-aware setup steps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fresh": {"type": "boolean", "description": "Rediscover now."},
                "scan_subnet": {"type": "boolean"},
            },
        },
    },
    {
        "name": "route_task",
        "description": "Recommend the cheapest model tier for a task and whether it "
                       "can be served by a local backend (to save cloud tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {"type": "string",
                              "description": "e.g. simple_qa, classification, code_review, "
                                             "architecture, security_audit."},
                "input_text": {"type": "string"},
                "complexity": {"type": "number", "description": "0.5 simple … 2.0 complex."},
            },
            "required": ["task_type", "input_text"],
        },
    },
    {
        "name": "local_chat",
        "description": "Run a prompt on a local model and return the result. Use for "
                       "classification, extraction, summaries, simple Q&A — keeps cloud "
                       "token usage at zero for that call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "system": {"type": "string"},
                "model": {"type": "string", "description": "Model id; default = backend's first."},
                "max_tokens": {"type": "integer", "default": 1024},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "auto_route",
        "description": "Auto-decide whether a task should run on a LOCAL model or a "
                       "CLOUD model (DeepSeek, GLM, Nemotron, Grok, Gemma, …) based on "
                       "an automatic effort estimate, then optionally execute it. "
                       "Cloud models need an API key (OPENROUTER_API_KEY or native).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "task_type": {"type": "string", "description": "Optional hint, e.g. code_review."},
                "execute": {"type": "boolean", "description": "Run it (true) or just decide (false)."},
                "max_tokens": {"type": "integer", "default": 512},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "fusion",
        "description": "Run a multi-model fusion strategy. cascade: cheap/local first, "
                       "escalate if low-confidence. draft_refine: local drafts, a stronger "
                       "cloud model refines. vote: ask several models, return consensus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "enum": ["cascade", "draft_refine", "vote"]},
                "prompt": {"type": "string"},
                "max_tokens": {"type": "integer", "default": 256},
            },
            "required": ["strategy", "prompt"],
        },
    },
    {
        "name": "find_skills",
        "description": "Find the skills/tools relevant to a task by searching SKILL.md "
                       "files locally — 0 cloud tokens (lexical match; optional local-LLM "
                       "rerank). Use this to pick tools instead of spending a cloud model "
                       "on skill search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "roots": {"type": "array", "items": {"type": "string"},
                          "description": "Skill dirs to search (default: repo skills/)."},
                "top_k": {"type": "integer", "default": 5},
                "use_local": {"type": "boolean", "description": "Local-LLM rerank (0 cloud tokens)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "infra_tips",
        "description": "Audit the local cluster's hardware/software/MCP setup and return "
                       "prioritized tips to cut token cost (GPU, Hailo NPU for vision, "
                       "Linux inference node, local Qdrant, …) plus an ASCII cluster diagram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scan_subnet": {"type": "boolean", "description": "Sweep the local /24 first."},
            },
        },
    },
    {
        "name": "auto_audit",
        "description": "One-pass cost audit on a project: agent directives health, infra "
                       "tips + ASCII diagram, duplicate-function scan, and local skill "
                       "catalog size, with pointers to deeper passes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project dir (default: cwd)."},
                "scan_subnet": {"type": "boolean"},
            },
        },
    },
    {
        "name": "improve_prompt",
        "description": "Rewrite a rough prompt into a professional, structured prompt "
                       "(role/context/task/instructions/constraints/output_format/success "
                       "criteria) using a LOCAL model — 0 cloud tokens. Set as_json for a "
                       "strict JSON prompt object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "as_json": {"type": "boolean", "description": "Return a JSON prompt object."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "metrics",
        "description": "Cost-focused project metrics: LOC by language/component, "
                       "duplicate-fn groups, directive health, always-on context cost "
                       "(CLAUDE.md tokens × turns), local-routing posture, and the "
                       "audit's own (≈0 token) cost.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project dir (default: cwd)."},
            },
        },
    },
    {
        "name": "scrape",
        "description": "Fetch a URL and extract clean title/text locally (stdlib, 0 cloud "
                       "tokens); set structure to have a LOCAL model summarise + pull entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "structure": {"type": "boolean", "description": "Local-model summary + entities."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "ingest_source",
        "description": "Scrape a URL (or take a file/text), reflect locally, and store it "
                       "in a Qdrant collection (the second-brain foundation) for later recall. "
                       "Embeddings auto-resolve a local /v1/embeddings endpoint from the registry "
                       "(real semantic vectors) and fall back to a deterministic hash vector "
                       "otherwise. 0 cloud tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "collection": {"type": "string", "default": "botte_ingest"},
                "qdrant": {"type": "string", "default": "192.168.1.47:6333"},
                "is_file": {"type": "boolean", "description": "source is a file/text, not a URL."},
                "embed_url": {"type": "string", "description": "override the /v1/embeddings endpoint."},
                "embed_model": {"type": "string", "description": "override the embedding model name."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "draft_doc",
        "description": "Draft documentation with a LOCAL model (0 cloud tokens), then refine "
                       "with the cloud only if a key is set. kind: readme|module|changelog|guide|adr.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "kind": {"type": "string"},
                "context": {"type": "string"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "session_review",
        "description": "Summarise locally what a work session did (done/decisions/learnings/"
                       "next) from a transcript file or raw text. 0 cloud tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "is_file": {"type": "boolean", "default": True},
            },
            "required": ["source"],
        },
    },
    {
        "name": "system_map",
        "description": "Show botte-secrète's own capability tree (the system as layers: "
                       "SENSE/DECIDE/ACT/REMEMBER/GOVERN/DEPLOY). Use to see what the "
                       "toolkit can do as a system.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "curate",
        "description": "Pick the botte-secrète capabilities most relevant to a goal "
                       "(local lexical match, 0 tokens) — the curator that hands you the "
                       "right tools for the task.",
        "inputSchema": {
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
        },
    },
    {
        "name": "dashboard",
        "description": "Generate one timestamped HTML dashboard of the cost picture: routing "
                       "savings, metric trends, metrics, and the cost of outstanding fixes.",
        "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}},
    },
    {
        "name": "estimate_cost",
        "description": "Estimate a task's cost: tokens, model/tier, money ($) and wall-time. "
                       "Use before running work to know what it costs (local = free).",
        "inputSchema": {"type": "object", "properties": {
            "task_type": {"type": "string"}, "input_chars": {"type": "integer"},
            "complexity": {"type": "number"}}, "required": ["task_type", "input_chars"]},
    },
    {
        "name": "fix_plan",
        "description": "List a project's correctable issues (dead code, duplication, stale "
                       "directive refs) with a tokens·model·money·time cost per fix and a total. "
                       "Plan-only — never edits code.",
        "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}},
    },
    {
        "name": "trends_show",
        "description": "Show a project's audit metrics over time + the change since the "
                       "previous run (directive score, duplication, LOC, always-on cost).",
        "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}},
    },
    {
        "name": "list_reports",
        "description": "List saved audit reports (timestamped .md/.html under "
                       ".botte/reports/) — consultable at any time.",
        "inputSchema": {"type": "object", "properties": {"dir": {"type": "string"}}},
    },
    {
        "name": "routing_stats",
        "description": "Routing control loop — measured outcomes (local %, token savings, "
                       "escalation/success rates) and a proposed threshold adjustment so the "
                       "router keeps more work local over time.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "conduct",
        "description": "Route a high-level goal to an ordered, local-first plan of "
                       "botte-secrète capabilities (which tools, in what order, what stays "
                       "local). The generalised router. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {"goal": {"type": "string"}},
                        "required": ["goal"]},
    },
    {
        "name": "execute_plan",
        "description": "Plan a goal AND run its read-only analysis steps (the conductor "
                       "executor). Mutating/generative/cloud steps are gated (run only with "
                       "confirm=true); steps with an unfilled <placeholder> are skipped. Use "
                       "dry_run=true to preview what would run. Read-only steps cost 0 cloud "
                       "tokens; returns per-step status + output.",
        "inputSchema": {"type": "object", "properties": {
            "goal": {"type": "string"},
            "confirm": {"type": "boolean"},
            "dry_run": {"type": "boolean"}},
            "required": ["goal"]},
    },
    {
        "name": "security_scan",
        "description": "Taint / data-flow security scan of a project (neuro-symbolic, "
                       "local-first). Traces attacker-controlled sources (argv, env, request, "
                       "input) into dangerous sinks (subprocess/eval/exec, SQL, pickle/yaml, "
                       "urlopen) and flags insecure-by-default calls, each CWE-tagged. Symbolic "
                       "pass is 0 tokens; set judge=true to confirm candidates with a LOCAL "
                       "model (0 cloud tokens). Python data-flow today.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "default": "."},
            "judge": {"type": "boolean"}},
        },
    },
    {
        "name": "docs_map",
        "description": "Scoped documentation map for a multi-component project (server/client/"
                       "tools/…). Detects components, classifies docs as global vs "
                       "component-scoped, and frames token cost so a coder bounded to one "
                       "component loads only its docs + linked globals — not every other "
                       "component's. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "default": "."}}},
    },
    {
        "name": "cluster_status",
        "description": "Show the homelab cluster: every reachable machine + its backends, "
                       "and the recommended target (LRU spread to idle boxes / fastest).",
        "inputSchema": {"type": "object", "properties": {"scan_subnet": {"type": "boolean"}}},
    },
]


# ── Tool implementations ─────────────────────────────────────────────────────

def _tool_discover_backends(args: dict) -> str:
    backends = registry.refresh(
        hosts=args.get("hosts") or None,
        scan_subnet=bool(args.get("scan_subnet", False)),
    )
    return json.dumps({
        "count": len(backends),
        "backends": [b.to_dict() for b in backends],
    }, ensure_ascii=False, indent=2)


def _tool_list_models(_args: dict) -> str:
    backends = registry.load()
    out = {f"{b.label} ({b.host}:{b.port})": b.models for b in backends}
    if not out:
        return "Registry empty — run discover_backends first."
    return json.dumps(out, ensure_ascii=False, indent=2)


def _tool_audit_local_usage(args: dict) -> str:
    return json.dumps(
        audit(fresh=bool(args.get("fresh", False)),
              scan_subnet=bool(args.get("scan_subnet", False))),
        ensure_ascii=False, indent=2,
    )


def _tool_route_task(args: dict) -> str:
    from skills.tiered_router import TieredRouter, Tier  # local import: heavier module
    router = TieredRouter()
    decision = router.route(
        args["task_type"], args.get("input_text", ""),
        complexity=float(args.get("complexity", 1.0)),
    )
    decision = dict(decision)
    decision["tier"] = decision["tier"].name if isinstance(decision["tier"], Tier) else decision["tier"]
    if "original_tier" in decision and isinstance(decision["original_tier"], Tier):
        decision["original_tier"] = decision["original_tier"].name
    # Attach a concrete local backend/model when local routing is possible.
    if decision.get("local_available"):
        best = registry.best_chat_backend()
        if best:
            decision["suggested_backend"] = f"{best.host}:{best.port}"
            decision["suggested_model"] = registry.preferred_model(best)
    return json.dumps(decision, ensure_ascii=False, indent=2)


def _tool_local_chat(args: dict) -> str:
    try:
        res = LocalLLMClient().chat(
            args["prompt"], system=args.get("system"),
            model=args.get("model"), max_tokens=int(args.get("max_tokens", 1024)),
        )
    except LocalLLMError as e:
        return f"ERROR: {e}"
    note = " (truncated)" if res.truncated else ""
    return (f"[{res.backend} · {res.model} · {res.total_tokens} local tok{note}]\n"
            f"{res.text}")


def _tool_auto_route(args: dict) -> str:
    from skills.auto_router import auto_route, auto_run
    if args.get("execute"):
        return json.dumps(auto_run(args["prompt"], task_type=args.get("task_type", ""),
                                   max_tokens=int(args.get("max_tokens", 512))),
                          ensure_ascii=False, indent=2)
    return json.dumps(auto_route(args["prompt"], args.get("task_type", "")),
                      ensure_ascii=False, indent=2)


def _tool_fusion(args: dict) -> str:
    from skills.auto_router import fusion
    fn = {"cascade": fusion.cascade, "draft_refine": fusion.draft_refine,
          "vote": fusion.vote}.get(args.get("strategy", ""))
    if not fn:
        return "ERROR: strategy must be cascade | draft_refine | vote"
    return json.dumps(fn(args["prompt"], max_tokens=int(args.get("max_tokens", 256))),
                      ensure_ascii=False, indent=2)


def _tool_find_skills(args: dict) -> str:
    from skills.skill_finder import find
    roots = [__import__("pathlib").Path(r).expanduser() for r in args.get("roots", [])] or None
    return json.dumps(
        find(args["query"], roots=roots, top_k=int(args.get("top_k", 5)),
             use_local=bool(args.get("use_local", False))),
        ensure_ascii=False, indent=2,
    )


def _tool_infra_tips(args: dict) -> str:
    from skills.infra_advisor import advise
    return json.dumps(advise(scan_subnet=bool(args.get("scan_subnet", False)), fresh=True),
                      ensure_ascii=False, indent=2)


def _tool_auto_audit(args: dict) -> str:
    from skills.infra_advisor import auto_audit
    return json.dumps(auto_audit(args.get("project", "."),
                                 scan_subnet=bool(args.get("scan_subnet", False))),
                      ensure_ascii=False, indent=2)


def _tool_improve_prompt(args: dict) -> str:
    from skills.prompt_improver import improve
    return json.dumps(improve(args["prompt"], as_json=bool(args.get("as_json", False))),
                      ensure_ascii=False, indent=2)


def _tool_metrics(args: dict) -> str:
    from skills.metrics import collect
    return json.dumps(collect(args.get("project", ".")).to_dict(),
                      ensure_ascii=False, indent=2)


def _tool_scrape(args: dict) -> str:
    from skills.ingest import scrape
    return json.dumps(scrape(args["url"], structure=bool(args.get("structure", False))).to_dict(),
                      ensure_ascii=False, indent=2)


def _tool_ingest_source(args: dict) -> str:
    from skills.ingest import ingest
    return json.dumps(ingest(args["source"], collection=args.get("collection", "botte_ingest"),
                             qdrant=args.get("qdrant", "192.168.1.47:6333"),
                             embed_url=args.get("embed_url"),
                             embed_model=args.get("embed_model"),
                             is_url=not bool(args.get("is_file", False))),
                      ensure_ascii=False, indent=2)


def _tool_draft_doc(args: dict) -> str:
    from skills.docgen import draft_doc
    return json.dumps(draft_doc(args["topic"], kind=args.get("kind", "guide"),
                                context=args.get("context", "")),
                      ensure_ascii=False, indent=2)


def _tool_session_review(args: dict) -> str:
    from skills.docgen import session_review
    return json.dumps(session_review(args["source"], is_file=bool(args.get("is_file", True))),
                      ensure_ascii=False, indent=2)


def _tool_dashboard(args: dict) -> str:
    from skills.dashboard import generate
    return json.dumps({"saved": generate(args.get("project", "."), fmt="html")},
                      ensure_ascii=False, indent=2)


def _tool_estimate_cost(args: dict) -> str:
    from skills.cost_estimator import estimate
    e = estimate(args["task_type"], int(args["input_chars"]),
                 complexity=float(args.get("complexity", 1.0)))
    return json.dumps({**e.to_dict(), "human": e.human()}, ensure_ascii=False, indent=2)


def _tool_fix_plan(args: dict) -> str:
    from skills.fix import find_fixes
    return json.dumps(find_fixes(args.get("project", ".")), ensure_ascii=False, indent=2)


def _tool_trends_show(args: dict) -> str:
    from skills.trends import show
    return json.dumps(show(args.get("project", ".")), ensure_ascii=False, indent=2)


def _tool_list_reports(args: dict) -> str:
    from skills.report import list_reports
    import pathlib
    d = args.get("dir") or ".botte/reports"
    return json.dumps(list_reports(pathlib.Path(d)), ensure_ascii=False, indent=2)


def _tool_routing_stats(_args: dict) -> str:
    from skills.control_loop.control_loop import analyze, adapt
    st = analyze()
    return json.dumps({"stats": st, "adapt": adapt(st)}, ensure_ascii=False, indent=2)


def _tool_conduct(args: dict) -> str:
    from skills.conductor import plan
    return json.dumps(plan(args["goal"]), ensure_ascii=False, indent=2)


def _tool_execute_plan(args: dict) -> str:
    from skills.conductor import run_goal
    r = run_goal(args["goal"], confirm=bool(args.get("confirm", False)),
                 dry_run=bool(args.get("dry_run", False)))
    return json.dumps(r, ensure_ascii=False, indent=2)


def _tool_security_scan(args: dict) -> str:
    from skills.fallow_like.config import FallowConfig
    from skills.fallow_like.cli import run_analysis
    cfg = FallowConfig(
        project_root=args.get("project", "."), taint_judge=bool(args.get("judge", False)),
        enable_dead_code=False, enable_duplication=False, enable_complexity=False,
        enable_boundaries=False, enable_feature_flags=False, enable_secrets=False,
        enable_hot_paths=False, enable_blast_radius=False,
    )
    result = run_analysis(cfg)
    findings = [f.model_dump() if hasattr(f, "model_dump") else dict(f)
                for f in result.taint]
    return json.dumps({"count": len(findings), "findings": findings},
                      ensure_ascii=False, indent=2, default=str)


def _tool_docs_map(args: dict) -> str:
    from skills.docs_steward import build_map
    return json.dumps(build_map(args.get("project", ".")),
                      ensure_ascii=False, indent=2)


def _tool_cluster_status(args: dict) -> str:
    from skills.cluster import status
    return json.dumps(status(scan_subnet=bool(args.get("scan_subnet", False))),
                      ensure_ascii=False, indent=2)


def _tool_system_map(_args: dict) -> str:
    from skills.capabilities import ascii_map
    return ascii_map()


def _tool_curate(args: dict) -> str:
    from skills.capabilities import curate
    return json.dumps(curate(args["goal"]), ensure_ascii=False, indent=2)


DISPATCH = {
    "dashboard": _tool_dashboard,
    "estimate_cost": _tool_estimate_cost,
    "fix_plan": _tool_fix_plan,
    "trends_show": _tool_trends_show,
    "list_reports": _tool_list_reports,
    "routing_stats": _tool_routing_stats,
    "conduct": _tool_conduct,
    "execute_plan": _tool_execute_plan,
    "security_scan": _tool_security_scan,
    "docs_map": _tool_docs_map,
    "cluster_status": _tool_cluster_status,
    "system_map": _tool_system_map,
    "curate": _tool_curate,
    "discover_backends": _tool_discover_backends,
    "list_models": _tool_list_models,
    "audit_local_usage": _tool_audit_local_usage,
    "route_task": _tool_route_task,
    "local_chat": _tool_local_chat,
    "auto_route": _tool_auto_route,
    "fusion": _tool_fusion,
    "find_skills": _tool_find_skills,
    "infra_tips": _tool_infra_tips,
    "auto_audit": _tool_auto_audit,
    "improve_prompt": _tool_improve_prompt,
    "metrics": _tool_metrics,
    "scrape": _tool_scrape,
    "ingest_source": _tool_ingest_source,
    "draft_doc": _tool_draft_doc,
    "session_review": _tool_session_review,
}


# ── JSON-RPC / MCP plumbing ──────────────────────────────────────────────────

def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(request: dict):
    """Return a response dict, or None for notifications (no reply)."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method in ("notifications/initialized", "initialized"):
        return None  # notification — no response

    if method == "ping":
        return _result(req_id, {})

    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        fn = DISPATCH.get(name)
        if not fn:
            return _error(req_id, -32602, f"Unknown tool: {name}")
        try:
            text = fn(args)
            return _result(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception as e:  # surface tool errors as MCP tool errors
            return _result(req_id, {
                "content": [{"type": "text", "text": f"ERROR: {e}"}],
                "isError": True,
            })

    if req_id is None:
        return None  # unknown notification
    return _error(req_id, -32601, f"Method not found: {method}")


def main() -> int:
    # stdout must carry only JSON-RPC; ensure UTF-8 and no buffering surprises.
    for stream in (sys.stdout, sys.stderr):
        rc = getattr(stream, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
