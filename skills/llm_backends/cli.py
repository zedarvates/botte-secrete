"""CLI for llm_backends — stdlib argparse, no external deps.

    python -m skills.llm_backends.cli scan [--subnet] [host ...]
    python -m skills.llm_backends.cli list
    python -m skills.llm_backends.cli audit [--fresh] [--subnet] [host ...]
    python -m skills.llm_backends.cli chat "your prompt" [--model M]
    python -m skills.llm_backends.cli profile <project_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skills.llm_backends import registry
from skills.llm_backends.audit import audit, PROJECT_MODEL_HINTS
from skills.llm_backends.client import LocalLLMClient, LocalLLMError


def _cmd_scan(args) -> int:
    backends = registry.refresh(
        hosts=args.hosts or None, scan_subnet=args.subnet, timeout=args.timeout
    )
    if not backends:
        print("No backends found. Is LM Studio / Ollama running?")
        return 1
    print(f"Registered {len(backends)} backend(s) → {registry.DEFAULT_REGISTRY_PATH}")
    for b in backends:
        models = ", ".join(b.models[:3]) + (" …" if len(b.models) > 3 else "")
        print(f"  {b.label:16s} {b.host}:{b.port}  {b.latency_ms}ms  [{models}]")
    return 0


def _cmd_list(_args) -> int:
    backends = registry.load()
    if not backends:
        print("Registry empty — run `scan` first.")
        return 1
    print(json.dumps([b.to_dict() for b in backends], indent=2, ensure_ascii=False))
    return 0


def _cmd_audit(args) -> int:
    report = audit(hosts=args.hosts or None, scan_subnet=args.subnet, fresh=args.fresh)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_chat(args) -> int:
    try:
        res = LocalLLMClient().chat(args.prompt, model=args.model,
                                    max_tokens=args.max_tokens)
    except LocalLLMError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"[{res.backend} · {res.model} · {res.total_tokens} tok]")
    print(res.text)
    return 0


def _cmd_profile(args) -> int:
    """Suggest a local model for a project based on its detected type."""
    ptype = "unknown"
    try:
        from skills.skill_project_optimizer.profiler import profile_project  # type: ignore
        prof = profile_project(Path(args.project))
        ptype = getattr(prof, "project_type", None) or (
            prof.get("project_type") if isinstance(prof, dict) else "unknown")
    except Exception:
        # Fallback heuristic if optimizer profiler is unavailable.
        p = Path(args.project)
        if (p / "package.json").exists():
            ptype = "web-frontend"
        elif (p / "pyproject.toml").exists() or (p / "requirements.txt").exists():
            ptype = "web-backend"
        elif (p / "Cargo.toml").exists():
            ptype = "cli"
    hint = PROJECT_MODEL_HINTS.get(ptype, PROJECT_MODEL_HINTS["unknown"])
    best = registry.best_chat_backend()
    print(json.dumps({
        "project": str(args.project),
        "project_type": ptype,
        "preferred_model_family": hint,
        "active_backend": f"{best.host}:{best.port}" if best else None,
        "active_models": best.models if best else [],
    }, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llm_backends", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="discover + register backends")
    s.add_argument("hosts", nargs="*", help="explicit hosts (default 127.0.0.1)")
    s.add_argument("--subnet", action="store_true", help="sweep local /24")
    s.add_argument("--timeout", type=float, default=1.0)
    s.set_defaults(func=_cmd_scan)

    s = sub.add_parser("list", help="print registered backends")
    s.set_defaults(func=_cmd_list)

    s = sub.add_parser("audit", help="local-usage audit + setup advice")
    s.add_argument("hosts", nargs="*")
    s.add_argument("--subnet", action="store_true")
    s.add_argument("--fresh", action="store_true", help="rediscover now")
    s.set_defaults(func=_cmd_audit)

    s = sub.add_parser("chat", help="run one prompt on the best local backend")
    s.add_argument("prompt")
    s.add_argument("--model", default=None)
    s.add_argument("--max-tokens", type=int, default=1024)
    s.set_defaults(func=_cmd_chat)

    s = sub.add_parser("profile", help="suggest a local model for a project")
    s.add_argument("project")
    s.set_defaults(func=_cmd_profile)

    return p


def _force_utf8_stdout() -> None:
    """Windows consoles default to cp1252 and choke on arrows/emoji."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
