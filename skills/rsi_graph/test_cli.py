from skills import cli

def test_top_level_cli_exposes_rsi():
    usage = cli._usage()
    assert "rsi" in usage
    assert cli._COMMANDS["rsi"][0] == "skills.rsi_graph.cli"
