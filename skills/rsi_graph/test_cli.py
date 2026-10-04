from skills import cli

def test_top_level_cli_exposes_rsi():
    usage = cli._usage()
    assert "rsi" in usage
    assert cli._COMMANDS["rsi"][0] == "skills.rsi_graph.cli"

def test_top_level_cli_reports_partial_read_only_input(tmp_path):
    import contextlib
    import io
    import json
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    original = '{"kind":"route-é"}\nnull\n'
    path.write_text(original, encoding="utf-8")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(["rsi", "observe", str(tmp_path), "--json"])
    graph = json.loads(output.getvalue())
    assert code == 0
    assert graph["source_status"] == "partial" and graph["rejected_records"] == 1
    assert graph["read_only"] is True and graph["event_count"] == 1
    assert path.read_text(encoding="utf-8") == original


def test_top_level_cli_fails_on_invalid_utf8(tmp_path):
    import contextlib
    import io
    import json
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    path.write_bytes(b"\xff")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(["rsi", "observe", str(tmp_path), "--json"])
    assert code == 2
    assert json.loads(output.getvalue())["source_status"] == "invalid"
    assert path.read_bytes() == b"\xff"


def test_top_level_cli_fails_on_unavailable_history(tmp_path):
    import contextlib
    import io
    import json
    from pathlib import Path
    from unittest.mock import patch
    output = io.StringIO()
    with patch.object(Path, "open", side_effect=PermissionError("synthetic input")):
        with contextlib.redirect_stdout(output):
            code = cli.main(["rsi", "observe", str(tmp_path), "--json"])
    assert code == 2
    assert json.loads(output.getvalue())["source_status"] == "unavailable"
