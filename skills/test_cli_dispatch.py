"""Regression tests for subcommand dispatch in the optimization CLIs."""

from skills.agent_compression import cli as agent_compression
from skills.agent_intel import cli as agent_intel
from skills.context_windows import cli as context_windows
from skills.dag_optimizer import cli as dag_optimizer
from skills.pipeline_integrator import cli as pipeline_integrator
from skills.token_compressor import cli as token_compressor


def test_cli_subcommands_are_executed(capsys):
    cases = [
        (agent_compression.main, ["stats"], "dict_size"),
        (agent_intel.main, ["predict-fix", "typo", "--budget", "50"], "estimated_tokens"),
        (context_windows.main, ["stats"], "windows"),
        (dag_optimizer.main, ["rag", "--query", "concise query"], "concise query"),
        (pipeline_integrator.main, ["health"], "healthy"),
        (token_compressor.main, ["hash", "hello"], "Hash:"),
    ]

    for main, argv, expected in cases:
        assert main(argv) == 0
        assert expected in capsys.readouterr().out


def test_predict_fix_estimate_is_independent_from_budget():
    intel = agent_intel.AgentIntel()
    low = intel.predict_fix("security vulnerability in authentication", budget=50)
    high = intel.predict_fix("security vulnerability in authentication", budget=5000)

    assert low["estimated_tokens"] == high["estimated_tokens"]
    assert low["worth_it"] is False
    assert high["worth_it"] is True
