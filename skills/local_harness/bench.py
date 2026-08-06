"""bench — measure what the harness does to a local model's hallucinations.

Same model outputs, two ways:
  * RAW       — the model answers, you trust it.
  * HARNESSED — the answer must pass deterministic verification, else it escalates.

The harness can't make a small model smarter, but it converts *confident wrong
answers* into *honest escalations* — so the hallucinations it returns drop to ~0.

Run live against your backend (real numbers for your model):
    python -m skills.local_harness.bench --live
Or deterministic (no backend, demonstrates the methodology / used in tests):
    python -m skills.local_harness.bench
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from skills.local_harness.spec import HarnessSpec
from skills.local_harness.executor import run_harness


@dataclass
class Task:
    id: str
    context: str
    question: str
    gold: str          # the correct, grounded answer ("" = not in context → a trap)
    mock: dict         # what a flawed local model would reply (used without --live)


# A small grounded-extraction set: some answerable, some hallucinated by the mock,
# some traps (answer absent from the context → the honest move is to escalate).
BENCH_TASKS = [
    Task("retries", "The client retries 3 times before giving up.",
         "How many retries?", "3", {"answer": "3", "evidence": ["retries 3 times"]}),
    Task("timeout", "Each request times out after 30 seconds.",
         "What is the timeout?", "30 seconds",
         {"answer": "30 seconds", "evidence": ["times out after 30 seconds"]}),
    Task("port", "The server listens on port 8080.",
         "Which port?", "8080", {"answer": "8080", "evidence": ["listens on port 8080"]}),
    Task("cache", "Responses are cached for 5 minutes.",
         "Cache duration?", "5 minutes", {"answer": "5 minutes", "evidence": ["cached for 5 minutes"]}),
    # mock hallucinates: invents an ungrounded 'evidence' span
    Task("workers", "The pool starts with 4 workers.",
         "How many workers?", "4", {"answer": "8", "evidence": ["starts with 8 workers"]}),
    Task("ttl", "The token TTL is 1 hour.",
         "Token TTL?", "1 hour", {"answer": "24 hours", "evidence": ["TTL is 24 hours"]}),
    Task("region", "Data is stored in the eu-west-1 region.",
         "Which region?", "eu-west-1", {"answer": "us-east-1", "evidence": ["stored in us-east-1"]}),
    # traps: the answer is NOT in the context; an honest model must escalate
    Task("ceo", "The service exposes a REST API over HTTPS.",
         "Who is the CEO?", "", {"answer": "Jane Doe", "evidence": ["CEO is Jane Doe"]}),
    Task("price", "The API returns JSON.",
         "What is the monthly price?", "", {"answer": "$49/mo", "evidence": ["price is $49/mo"]}),
]

_SPEC = HarnessSpec(
    max_effort=1.0,  # the tasks are easy; let the verifier (not the gate) do the work
    output_schema={"type": "object", "required": ["answer", "evidence"],
                   "properties": {"answer": {"type": "string"}, "evidence": {"type": "array"}}},
    verify=["schema", "evidence_in_context"],
    ground_source="files:.", on_fail="escalate",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def _is_correct(output: dict, task: Task) -> bool:
    """A raw answer is 'correct' only if it matches the gold AND is grounded."""
    if not task.gold:                       # trap: any concrete answer is wrong
        return False
    ans = _norm(output.get("answer", ""))
    ev_ok = any(_norm(e) and _norm(e) in _norm(task.context)
                for e in (output.get("evidence") or []))
    return _norm(task.gold) in ans and ev_ok


def run_bench(get_output: Callable[[Task], dict]) -> dict:
    """get_output(task) -> the model's JSON reply (real client or mock).

    Returns counts for RAW (trust the model) vs HARNESSED (verify-or-escalate)."""
    raw_correct = 0
    raw_hallucinated = 0
    trusted_correct = 0
    escalated = 0
    abstained = 0
    hallucinated_returned = 0

    for task in BENCH_TASKS:
        out = get_output(task)
        # RAW: you trust whatever the model said.
        if _is_correct(out, task):
            raw_correct += 1
        else:
            raw_hallucinated += 1

        # HARNESSED: same output, but it must pass verification.
        stub = type("_C", (), {"chat_json": lambda self, p, _o=out, **k: _o})()
        r = run_harness(_SPEC, task.question, context=task.context, client=stub,
                        effort_fn=lambda t, tt: 0.1,
                        escalate_fn=lambda t, tier: "(escalated to cloud)")
        if r.source == "local":
            if _is_correct(r.answer, task):
                trusted_correct += 1
            else:
                hallucinated_returned += 1   # verify let a bad answer through
        elif r.source == "abstained":
            abstained += 1
        else:
            escalated += 1

    n = len(BENCH_TASKS)
    return {
        "n": n,
        "raw": {"correct": raw_correct, "hallucinated": raw_hallucinated},
        "harnessed": {
            "trusted_correct": trusted_correct,
            "escalated": escalated,
            "abstained": abstained,
            "hallucinated_returned": hallucinated_returned,
        },
        "raw_hallucination_rate": round(raw_hallucinated / n, 3),
        "harnessed_hallucination_rate": round(hallucinated_returned / n, 3),
    }


def format_report(rep: dict) -> str:
    n, raw, h = rep["n"], rep["raw"], rep["harnessed"]
    pct = lambda x: f"{100 * x / n:.0f}%"
    return "\n".join([
        f"Hallucination bench — {n} grounded tasks",
        "",
        f"  WITHOUT harness:  {raw['correct']} correct, "
        f"{raw['hallucinated']} hallucinated  → {pct(raw['hallucinated'])} hallucination rate",
        f"  WITH harness:     {h['trusted_correct']} trusted-correct, "
        f"{h['escalated']} escalated, {h['abstained']} abstained, "
        f"{h['hallucinated_returned']} hallucinated  → {pct(h['hallucinated_returned'])} hallucination rate",
        "",
        f"  Headline: returned hallucinations {pct(raw['hallucinated'])} → "
        f"{pct(h['hallucinated_returned'])}; the rest escalate honestly instead of lying.",
    ])


def _mock_output(task: Task) -> dict:
    return task.mock


def _live_output(client):
    schema = _SPEC.output_schema

    def get(task: Task) -> dict:
        prompt = (f"Answer ONLY from the context. If absent, reply "
                  f"{{\"answer\": \"\", \"evidence\": []}}.\n\nContext: {task.context}\n\n"
                  f"Question: {task.question}")
        try:
            return client.chat_json(prompt, schema=schema, max_tokens=256)
        except Exception:  # noqa: BLE001
            return {"answer": "", "evidence": []}
    return get


def main(argv=None) -> int:
    import sys
    try:  # Windows cp1252 consoles crash on the → in the report.
        from skills.console_utf8 import force_utf8
        force_utf8()
    except Exception:  # noqa: BLE001
        pass
    argv = sys.argv[1:] if argv is None else argv
    if "--live" in argv:
        from skills.llm_backends.client import LocalLLMClient, LocalLLMError
        try:
            get = _live_output(LocalLLMClient())
        except LocalLLMError as e:
            print(f"No local backend ({e}); run without --live for the deterministic demo.")
            return 1
    else:
        get = _mock_output
        print("(deterministic mock — pass --live to benchmark your real local model)\n")
    print(format_report(run_bench(get)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
