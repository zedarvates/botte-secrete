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

Lazy tool loading (skills/llm_mcp/lazy.py, default on): tools/list returns only a
small core set + find_tool(query) instead of every tool's full schema — that
alone was ~3.3k tokens of always-on prefix (measured by context_profiler). Call
find_tool to discover and load the schema for anything else; tools/call still
dispatches ANY tool by name regardless of what was listed. Disable with
BOTTE_MCP_LAZY_TOOLS=0 for a client that doesn't expect a search step.

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
                "project": {"type": "string", "description": "Project root for the private QA ledger."},
                "execution_id": {"type": "string", "description": "Stable replay id; persisted only as a hash."},
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
        "name": "route_feedback",
        "description": "Attach an explicit local/cloud verdict to a prior auto_route "
                       "feedback_id. Only verified verdicts become binary_router "
                       "training data; backend success/failure alone never does.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feedback_id": {"type": "string",
                                "description": "Identifier returned by executed auto_route."},
                "correct_route": {"type": "string", "enum": ["local", "cloud"]},
            },
            "required": ["feedback_id", "correct_route"],
        },
    },
    {
        "name": "qa_advise",
        "description": "Return explainable quality advice: a shadow-only kNN route "
                       "suggestion from externally verified project outcomes. It never executes or changes "
                       "the active router, and high-risk work keeps a human gate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "project": {"type": "string", "description": "Project dir (default: cwd)."},
                "task_type": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "risk": {"type": "string",
                         "enum": ["low", "standard", "high", "critical"],
                         "default": "standard"},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 7},
            },
            "required": ["task"],
        },
    },
    {
        "name": "qa_record",
        "description": "Record one externally verified quality outcome in the project's "
                       "private support set. Raw task text is hashed into local features; "
                       "model self-reports are rejected as labels; at least one "
                       "external evidence reference is required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "project": {"type": "string", "description": "Project dir (default: cwd)."},
                "route": {"type": "string",
                          "enum": ["deterministic", "local", "cloud", "human"]},
                "verdict": {"type": "string",
                            "enum": ["FAIL", "UNCERTAIN", "PASS", "PASS_ROBUST"]},
                "verified_by": {"type": "string",
                                "description": "External verifier, e.g. tests:pytest or human:review."},
                "quality_score": {"type": "number", "minimum": 0, "maximum": 1},
                "risk": {"type": "string",
                         "enum": ["low", "standard", "high", "critical"],
                         "default": "standard"},
                "task_type": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"},
                "harness": {"type": "string"},
                "duration_ms": {"type": "number", "minimum": 0},
                "cost_usd": {"type": "number", "minimum": 0},
                "tokens": {"type": "integer", "minimum": 0},
                "evidence_refs": {"type": "array", "minItems": 1, "maxItems": 20,
                                  "items": {"type": "string"}},
            },
            "required": ["task", "route", "verdict", "verified_by", "evidence_refs"],
        },
    },
    {
        "name": "qa_status",
        "description": "Show verified support, maturity, privacy posture, and the single "
                       "next step for the project's shadow quality compass.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project dir (default: cwd)."},
            },
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
        "name": "scan_malicious",
        "description": "Scan a project's code for dangerous/obfuscated/malicious patterns "
                       "(eval/exec of decoded data, base64+exec, dynamic import, exfiltration, "
                       "suspicious subprocess/network) via regex + AST. Supply-chain self-check "
                       "for tools/skills before trusting them. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "default": "."}},
        },
    },
    {
        "name": "nn_audit",
        "description": "Audit the micro-NNs (skills/botte_nn): per model, is it grounded in "
                       "REAL data or a synthetic copy of a hand rule? Reports data_source, "
                       "provenance metadata, test guard, and a grounded/synthetic verdict — a "
                       "net trained on np.random just mimics a rule. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "default": "skills/botte_nn"}},
        },
    },
    {
        "name": "context_profile",
        "description": "Measure a project's always-on prefix (directives + core rules + MCP "
                       "tool schemas + skill catalogue) in tokens and as a % of small local "
                       "windows (64k/128k/256k), with a reduction plan (lazy tools, on-demand "
                       "skill search). Helps modest machines fit a usable local context. 0 tokens.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "default": "."}},
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
        "name": "context_budget",
        "description": "Pick the optimal set of skills to load for a task under a token "
                       "budget — an exact 0/1 knapsack (maximize relevance, stay under "
                       "budget), not an LLM 'what's relevant' call. Cuts the always-on "
                       "context cost; returns the chosen set + tokens saved vs the whole "
                       "catalog. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"},
            "budget": {"type": "integer", "default": 4000}},
            "required": ["query"]},
    },
    {
        "name": "nlp_classify",
        "description": "Deterministic intent classification — pick the best label for text "
                       "from {label: keywords} via lexical overlap + a local embedding "
                       "signal. No LLM call (0 cloud tokens), instant, repeatable. Use "
                       "instead of asking a model to classify.",
        "inputSchema": {"type": "object", "properties": {
            "text": {"type": "string"},
            "intents": {"type": "object",
                        "description": "{label: [keywords...]} map of candidate intents."}},
            "required": ["text", "intents"]},
    },
    {
        "name": "nlp_extract",
        "description": "Deterministic entity extraction — pull urls, emails, IPs, file "
                       "paths, env vars, CLI flags and numbers out of text via regex. "
                       "0 cloud tokens. Use instead of asking a model to extract entities.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                        "required": ["text"]},
    },
    {
        "name": "schedule_plan",
        "description": "Order plan steps under precedence constraints into a valid sequence "
                       "+ parallel waves (deterministic DAG topo sort, cycle-detecting). No "
                       "LLM 'figure out the order' call — 0 cloud tokens. deps = {step:[prereqs]}.",
        "inputSchema": {"type": "object", "properties": {
            "steps": {"type": "array", "items": {"type": "string"}},
            "deps": {"type": "object", "description": "{step: [prerequisite steps]}"}},
            "required": ["steps"]},
    },
    {
        "name": "assign_work",
        "description": "Balance (name:cost) tasks across workers/backends to minimize the "
                       "makespan (LPT greedy) — an exact-ish deterministic scheduler for "
                       "spreading cluster work. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "tasks": {"type": "array", "description": "[[name, cost], …]"},
            "workers": {"type": "array", "items": {"type": "string"}}},
            "required": ["tasks", "workers"]},
    },
    {
        "name": "cwe_explain",
        "description": "Explain a security weakness from the local CWE knowledge base: an "
                       "exact entry by id (e.g. CWE-78) or the best matches for free text "
                       "(local embedding) — name, description, mitigation. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "cwe_id": {"type": "string", "description": "e.g. CWE-78 (optional)."},
            "text": {"type": "string", "description": "free text to match if no id."}}},
    },
    {
        "name": "docs_lifecycle",
        "description": "Docs lifecycle summary for a project: finished tasks still sitting in "
                       "plan/TODO markdown (token waste an LLM keeps re-reading), fully-done "
                       "plans to archive, and `.botte` report proliferation (keep N recent). "
                       "Read-only; prune/archive are confirm-gated CLI actions. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "default": "."},
            "keep": {"type": "integer", "default": 5}}},
    },
    {
        "name": "cluster_status",
        "description": "Show the homelab cluster: every reachable machine + its backends, "
                       "and the recommended target (LRU spread to idle boxes / fastest).",
        "inputSchema": {"type": "object", "properties": {"scan_subnet": {"type": "boolean"}}},
    },
    {
        "name": "bench_run",
        "description": "Run the botte-secrete benchmark and return savings metrics "
                       "(token savings, routing accuracy, local-vs-cloud ratio). 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "description": "Project path. Default: current."}}},
    },
    {
        "name": "doctor",
        "description": "Full project health checkup — directives, infra, security, "
                       "micro-NN grounding, host prefix analysis. Equivalent to checkup CLI. "
                       "0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "description": "Project path. Default: current."}}},
    },
    {
        "name": "fleet_status",
        "description": "Aggregate fleet status across all registered projects — "
                       "token savings, routing stats, drift items per project.",
        "inputSchema": {"type": "object", "properties": {
            "sort": {"type": "string", "description": "Sort by: tokens_saved, loc, fixes."}}},
    },
    {
        "name": "compress",
        "description": "Compress text/JSON/logs/tool-output before sending it to an LLM "
                       "(universal_compressor) — returns the compressed content + ratio. "
                       "0 cloud tokens.",
        "inputSchema": {"type": "object", "required": ["content"], "properties": {
            "content": {"type": "string", "description": "Content to compress."},
            "content_type": {"type": "string",
                             "description": "auto|text|json|log|tool_output|code (default auto)."},
            "reversible": {"type": "boolean", "default": False,
                           "description": "Store the original for exact restoration and verified grounding."}}},
    },
    {
        "name": "shape_query",
        "description": "Classify a query's effort and return the adaptive token-shaping "
                       "profile (compression ratio, output-token target, verbosity steer) "
                       "from token_shaper. 0 cloud tokens.",
        "inputSchema": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "The user query to shape."},
            "agent_type": {"type": "string", "description": "Agent type (audit, fix, ...)."},
            "context_size": {"type": "number", "description": "Current context size in tokens."}}},
    },
    {
        "name": "belt2_hint",
        "description": "Run the Belt 2.0 micro-NN predictors (compressibility, pruning, "
                       "skip-agent, cloud escalation, response length, tool call, semantic "
                       "cache) on a task and return their hints. 0 cloud tokens.",
        "inputSchema": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Task text."},
            "agent_type": {"type": "string", "description": "Agent type (default audit)."},
            "task_type": {"type": "string", "description": "Task type (default analyze)."},
            "criticality": {"type": "number", "description": "0..1 (default 0.5)."}}},
    },
    {
        "name": "loop_decide",
        "description": "Propose a deterministic loop action without executing a tool or model. "
                       "The proposal is logged locally for shadow evaluation.",
        "inputSchema": {"type": "object", "required": ["loop_id", "goal"], "properties": {
            "loop_id": {"type": "string"}, "goal": {"type": "string"},
            "allowed_tools": {"type": "array", "items": {"type": "string"}},
            "iteration": {"type": "integer", "default": 0},
            "criticality": {"type": "number", "default": 0.5},
            "project": {"type": "string", "default": "."}}},
    },
    {
        "name": "loop_explain",
        "description": "Explain the cost-ordered loop decision and the layers avoided. No execution.",
        "inputSchema": {"type": "object", "required": ["loop_id", "goal"], "properties": {
            "loop_id": {"type": "string"}, "goal": {"type": "string"},
            "allowed_tools": {"type": "array", "items": {"type": "string"}},
            "iteration": {"type": "integer", "default": 0},
            "criticality": {"type": "number", "default": 0.5},
            "project": {"type": "string", "default": "."}}},
    },
    {
        "name": "loop_record",
        "description": "Append a verified loop outcome to the local ledger. Does not execute anything.",
        "inputSchema": {"type": "object", "required": ["loop_id", "iteration", "action", "progress"], "properties": {
            "loop_id": {"type": "string"}, "iteration": {"type": "integer"},
            "action": {"type": "string"}, "progress": {"type": "string"},
            "context_tokens": {"type": "integer", "default": 0},
            "execution_tokens": {"type": "integer", "default": 0},
            "verification_tokens": {"type": "integer", "default": 0},
            "cloud_tokens": {"type": "integer", "default": 0},
            "success": {"type": "boolean", "default": False},
            "cache_hit": {"type": "boolean", "default": False},
            "project": {"type": "string", "default": "."}}},
    },
    {
        "name": "loop_stats",
        "description": "Read local aggregate loop metrics from the append-only ledger. No network.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_hub",
        "description": "Search governed memory hub",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string"
                },
                "query": {
                    "type": "string"
                },
                "asset_type": {
                    "type": "string",
                    "enum": [
                        "chat_memory",
                        "skill",
                        "wiki",
                        "code_graph",
                        "fact",
                        "pattern",
                        "decision"
                    ]
                },
                "status": {
                    "type": "string",
                    "enum": [
                        "proposal",
                        "review_active",
                        "promoted",
                        "expired",
                        "obsoleted"
                    ]
                },
                "agent_id": {
                    "type": "string"
                },
                "limit": {
                    "type": "integer"
                }
            },
            "required": [
                "project_id"
            ]
        }
    },
    {
        "name": "context_bundle",
        "description": "Top-N memory for agent context",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string"
                },
                "agent_id": {
                    "type": "string"
                },
                "max_entries": {
                    "type": "integer"
                }
            },
            "required": [
                "project_id",
                "agent_id"
            ]
        }
    },
    {
        "name": "propose_memory",
        "description": "Propose new memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string"
                },
                "key": {
                    "type": "string"
                },
                "value": {
                    "description": "JSON value"
                },
                "asset_type": {
                    "type": "string",
                    "enum": [
                        "chat_memory",
                        "skill",
                        "wiki",
                        "code_graph",
                        "fact",
                        "pattern",
                        "decision"
                    ]
                },
                "category": {
                    "type": "string"
                },
                "confidence": {
                    "type": "number"
                },
                "agent_id": {
                    "type": "string"
                },
                "source_ref": {
                    "type": "string"
                },
                "visibility": {
                    "type": "string",
                    "enum": [
                        "private",
                        "project",
                        "team",
                        "restricted"
                    ]
                },
                "expires_in_days": {
                    "type": "number"
                },
                "tags": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": [
                "project_id",
                "key",
                "value",
                "agent_id"
            ]
        }
    },
    {
        "name": "promote_memory",
        "description": "Promote memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string"
                },
                "key": {
                    "type": "string"
                },
                "new_status": {
                    "type": "string",
                    "enum": [
                        "proposal",
                        "review_active",
                        "promoted",
                        "expired",
                        "obsoleted"
                    ]
                },
                "actor_id": {
                    "type": "string"
                }
            },
            "required": [
                "project_id",
                "key",
                "new_status",
                "actor_id"
            ]
        }
    },
    {
        "name": "forget_memory",
        "description": "Delete memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string"
                },
                "key": {
                    "type": "string"
                },
                "actor_id": {
                    "type": "string"
                }
            },
            "required": [
                "project_id",
                "key",
                "actor_id"
            ]
        }
    }
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
                                   max_tokens=int(args.get("max_tokens", 512)),
                                   project_root=args.get("project", "."),
                                   execution_id=args.get("execution_id", "")),
                          ensure_ascii=False, indent=2)
    return json.dumps(auto_route(args["prompt"], args.get("task_type", "")),
                      ensure_ascii=False, indent=2)


def _tool_route_feedback(args: dict) -> str:
    from skills.botte_nn.active_learning import record_verdict
    route = args["correct_route"]
    if route not in ("local", "cloud"):
        raise ValueError("correct_route must be local or cloud")
    verdict_id = record_verdict(args["feedback_id"], 0 if route == "local" else 1)
    return json.dumps({"feedback_id": args["feedback_id"], "correct_route": route,
                       "verdict_id": verdict_id, "verified": True},
                      ensure_ascii=False, indent=2)


def _tool_qa_advise(args: dict) -> str:
    from skills.trajectory.quality import advise_route
    advice = advise_route(
        args["task"],
        project_root=args.get("project", "."),
        task_type=args.get("task_type", ""),
        tags=args.get("tags", []),
        risk=args.get("risk", "standard"),
        k=int(args.get("k", 7)),
    )
    return json.dumps(advice.to_dict(), ensure_ascii=False, indent=2)


def _tool_qa_record(args: dict) -> str:
    from skills.trajectory.quality import record_verified
    record = record_verified(
        args["task"],
        project_root=args.get("project", "."),
        route=args["route"],
        verdict=args["verdict"],
        verified_by=args["verified_by"],
        quality_score=args.get("quality_score"),
        risk=args.get("risk", "standard"),
        task_type=args.get("task_type", ""),
        tags=args.get("tags", []),
        model=args.get("model", ""),
        harness=args.get("harness", ""),
        duration_ms=args.get("duration_ms"),
        cost_usd=args.get("cost_usd"),
        tokens=args.get("tokens"),
        evidence_refs=args.get("evidence_refs", []),
    )
    return json.dumps(record, ensure_ascii=False, indent=2)


def _tool_qa_status(args: dict) -> str:
    from skills.trajectory.quality import quality_status
    return json.dumps(quality_status(args.get("project", ".")),
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


def _tool_context_profile(args: dict) -> str:
    from skills.context_profiler import profile
    return json.dumps(profile(args.get("project", ".")), ensure_ascii=False, indent=2)


def _tool_nn_audit(args: dict) -> str:
    from skills.nn_audit import audit_models
    return json.dumps(audit_models(args.get("path", "skills/botte_nn")),
                      ensure_ascii=False, indent=2)


def _tool_scan_malicious(args: dict) -> str:
    from skills.security_scanner import scan_dir, scan_report
    findings = scan_dir(str(args.get("project", ".")), fail_on="info")  # all severities
    rep = scan_report(findings)
    return json.dumps({"count": rep.count, "by_severity": rep.by_severity,
                       "findings": [vars(f) for f in findings]},
                      ensure_ascii=False, indent=2, default=str)


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
    try:
        from skills.cwe_kb import enrich  # attach CWE name/description/mitigation
        findings = enrich(result.taint)
    except Exception:
        findings = [f.model_dump() if hasattr(f, "model_dump") else dict(f)
                    for f in result.taint]
    return json.dumps({"count": len(findings), "findings": findings},
                      ensure_ascii=False, indent=2, default=str)


def _tool_docs_map(args: dict) -> str:
    from skills.docs_steward import build_map
    return json.dumps(build_map(args.get("project", ".")),
                      ensure_ascii=False, indent=2)


def _tool_context_budget(args: dict) -> str:
    from skills.context_budget import select_skills
    return json.dumps(select_skills(args["query"], budget=int(args.get("budget", 4000))),
                      ensure_ascii=False, indent=2)


def _tool_nlp_classify(args: dict) -> str:
    from skills.nlp_deterministic import classify
    return json.dumps(classify(args["text"], args["intents"]),
                      ensure_ascii=False, indent=2)


def _tool_nlp_extract(args: dict) -> str:
    from skills.nlp_deterministic import extract_entities
    return json.dumps(extract_entities(args["text"]), ensure_ascii=False, indent=2)


def _tool_schedule_plan(args: dict) -> str:
    from skills.solvers import schedule
    return json.dumps(schedule(args["steps"], args.get("deps")),
                      ensure_ascii=False, indent=2)


def _tool_assign_work(args: dict) -> str:
    from skills.solvers import assign_balanced
    return json.dumps(assign_balanced(args["tasks"], args["workers"]),
                      ensure_ascii=False, indent=2)


def _tool_cwe_explain(args: dict) -> str:
    from skills.cwe_kb import explain
    return json.dumps(explain(cwe_id=args.get("cwe_id", ""), text=args.get("text", "")),
                      ensure_ascii=False, indent=2)


def _tool_docs_lifecycle(args: dict) -> str:
    from skills.docs_steward import lifecycle_report
    return json.dumps(lifecycle_report(args.get("project", "."),
                                       keep=int(args.get("keep", 5))),
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


def _tool_bench_run(args: dict) -> str:
    from skills.bench.bench import run as _bench_run
    return json.dumps(_bench_run(), ensure_ascii=False, indent=2, default=str)


def _tool_doctor(args: dict) -> str:
    from pathlib import Path as _P
    from skills.checkup.cli import doctor as _doctor
    return json.dumps(_doctor(_P(args.get("project", "."))),
                      ensure_ascii=False, indent=2, default=str)


def _tool_fleet_status(args: dict) -> str:
    from skills.dashboard import fleet as _fleet
    return json.dumps(_fleet.aggregate(), ensure_ascii=False, indent=2, default=str)


def _tool_compress(args: dict) -> str:
    import dataclasses
    from skills.universal_compressor.compressor import compress as _compress
    r = _compress(
        args["content"], args.get("content_type", "auto"),
        reversible=bool(args.get("reversible", False)), learn=True,
    )
    return json.dumps(dataclasses.asdict(r), ensure_ascii=False, indent=2)


def _tool_shape_query(args: dict) -> str:
    from skills.token_shaper.shaper import TokenShaper
    cfg = TokenShaper().shape(args["query"], args.get("agent_type", ""),
                              int(args.get("context_size", 0)))
    return json.dumps({"level": cfg.level.value, "compress_ratio": cfg.compress_ratio,
                       "output_tokens_target": cfg.output_tokens_target,
                       "skip_cache": cfg.skip_cache, "verbosity_steer": cfg.verbosity_steer,
                       "retain_thinking": cfg.retain_thinking},
                      ensure_ascii=False, indent=2)


def _tool_belt2_hint(args: dict) -> str:
    from skills.auto_router import nn_belt2
    hints = nn_belt2.full_belt_hint(
        text=args.get("text", ""), agent_type=args.get("agent_type", "audit"),
        task_type=args.get("task_type", "analyze"),
        criticality=float(args.get("criticality", 0.5)))
    out = {k: ({"label": v[0], "confidence": round(v[1], 3)} if v else "abstain")
           for k, v in hints.items()}
    return json.dumps(out, ensure_ascii=False, indent=2)


def _loop_request_state(args: dict):
    from skills.loop_optimizer.models import LoopRequest, LoopState
    request = LoopRequest(args["loop_id"], args["goal"],
                          criticality=float(args.get("criticality", 0.5)),
                          allowed_tools=tuple(args.get("allowed_tools", [])))
    state = LoopState(args["loop_id"], iteration=int(args.get("iteration", 0)))
    return request, state


def _tool_loop_decide(args: dict) -> str:
    from skills.loop_optimizer.controller import LoopController
    request, state = _loop_request_state(args)
    decision = LoopController(project_root=args.get("project", ".")).decide(request, state)
    return json.dumps(decision.to_dict(), ensure_ascii=False, separators=(",", ":"))


def _tool_loop_explain(args: dict) -> str:
    from skills.loop_optimizer.controller import LoopController
    request, state = _loop_request_state(args)
    return json.dumps(LoopController(project_root=args.get("project", ".")).explain(request, state),
                      ensure_ascii=False, separators=(",", ":"))


def _tool_loop_record(args: dict) -> str:
    from skills.loop_optimizer.controller import LoopController
    from skills.loop_optimizer.models import LoopOutcome
    fields = {name: args.get(name, default) for name, default in (
        ("context_tokens", 0), ("execution_tokens", 0), ("verification_tokens", 0),
        ("cloud_tokens", 0), ("success", False), ("cache_hit", False))}
    outcome = LoopOutcome(args["loop_id"], int(args["iteration"]), args["action"],
                          args["progress"], **fields)
    record = LoopController(project_root=args.get("project", ".")).record(outcome)
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _tool_loop_stats(_args: dict) -> str:
    from skills.loop_optimizer.ledger import LoopLedger
    ledger = LoopLedger()

def _tool_search_hub(args: dict) -> str:
    from skills.memory_hub.mcp import dispatch as _mh
    import json
    return json.dumps(_mh("search_hub", args), ensure_ascii=False)

def _tool_context_bundle(args: dict) -> str:
    from skills.memory_hub.mcp import dispatch as _mh
    import json
    return json.dumps(_mh("context_bundle", args), ensure_ascii=False)

def _tool_propose_memory(args: dict) -> str:
    from skills.memory_hub.mcp import dispatch as _mh
    import json
    return json.dumps(_mh("propose_memory", args), ensure_ascii=False)

def _tool_promote_memory(args: dict) -> str:
    from skills.memory_hub.mcp import dispatch as _mh
    import json
    return json.dumps(_mh("promote_memory", args), ensure_ascii=False)

def _tool_forget_memory(args: dict) -> str:
    from skills.memory_hub.mcp import dispatch as _mh
    import json
    return json.dumps(_mh("forget_memory", args), ensure_ascii=False)

    return json.dumps(ledger.summarize(ledger.read()), ensure_ascii=False, separators=(",", ":"))


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
    "scan_malicious": _tool_scan_malicious,
    "nn_audit": _tool_nn_audit,
    "context_profile": _tool_context_profile,
    "docs_map": _tool_docs_map,
    "docs_lifecycle": _tool_docs_lifecycle,
    "cwe_explain": _tool_cwe_explain,
    "context_budget": _tool_context_budget,
    "nlp_classify": _tool_nlp_classify,
    "nlp_extract": _tool_nlp_extract,
    "schedule_plan": _tool_schedule_plan,
    "assign_work": _tool_assign_work,
    "cluster_status": _tool_cluster_status,
    "system_map": _tool_system_map,
    "curate": _tool_curate,
    "discover_backends": _tool_discover_backends,
    "list_models": _tool_list_models,
    "audit_local_usage": _tool_audit_local_usage,
    "route_task": _tool_route_task,
    "local_chat": _tool_local_chat,
    "auto_route": _tool_auto_route,
    "route_feedback": _tool_route_feedback,
    "qa_advise": _tool_qa_advise,
    "qa_record": _tool_qa_record,
    "qa_status": _tool_qa_status,
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
    "bench_run": _tool_bench_run,
    "doctor": _tool_doctor,
    "fleet_status": _tool_fleet_status,
    "compress": _tool_compress,
    "shape_query": _tool_shape_query,
    "belt2_hint": _tool_belt2_hint,
    "loop_decide": _tool_loop_decide,
    "loop_explain": _tool_loop_explain,
    "loop_record": _tool_loop_record,
    "loop_stats": _tool_loop_stats,
    "search_hub": _tool_search_hub,
    "context_bundle": _tool_context_bundle,
    "propose_memory": _tool_propose_memory,
    "promote_memory": _tool_promote_memory,
    "forget_memory": _tool_forget_memory,
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
        from skills.llm_mcp.lazy import lazy_tool_list, lazy_enabled
        return _result(req_id, {"tools": lazy_tool_list(TOOLS) if lazy_enabled() else TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        if name == "find_tool":
            from skills.llm_mcp.lazy import find_tool
            import json as _json
            text = _json.dumps(find_tool(args.get("query", ""), TOOLS,
                                         top_k=int(args.get("top_k", 5))),
                               ensure_ascii=False, indent=2)
            return _result(req_id, {"content": [{"type": "text", "text": text}]})
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
