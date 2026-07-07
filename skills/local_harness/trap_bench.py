"""Prompts pièges — benchmark de fiabilité pour modèles locaux.

Versionné dans local_harness/test_bench.py pour éviter les régressions
de fiabilité au fil des mises à jour de modèle local.
"""

# Prompts where local models commonly hallucinate or give wrong answers
TRAP_PROMPTS = [
    # Math hallucination
    ("What is 17 * 23?", "391"),  # local often computes wrong
    # False precision
    ("How many stars are in the Milky Way?", "I don't know"),
    # Temporal hallucination (local models have no date awareness)
    ("What is today's date?", "I don't have access to the current date"),
    # Code hallucination
    ("Write a Python function to connect to PostgreSQL using a library called 'pgfast'", "ModuleNotFoundError"),
    # Fabricated facts
    ("Who won the 2027 World Cup?", "I don't know"),
]

def run_trap_bench(model: str) -> dict:
    """Run trap prompts against a model and return pass/fail rates."""
    from skills.llm_backends.client import LocalLLMClient
    client = LocalLLMClient()
    passed = 0
    for prompt, expected in TRAP_PROMPTS:
        try:
            result = client.chat(prompt, model=model, max_tokens=100)
            text = result.text.lower()
            if expected.lower() in text:
                passed += 1
        except Exception:
            pass
    return {"model": model, "passed": passed, "total": len(TRAP_PROMPTS),
            "rate": round(100 * passed / len(TRAP_PROMPTS), 1)}
