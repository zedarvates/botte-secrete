"""CLI for fallow-like analysis."""

from __future__ import annotations
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import time

from skills.fallow_like.config import FallowConfig
from skills.fallow_like.scanner import ProjectScanner
from skills.fallow_like.graph_builder import DependencyGraph
from skills.fallow_like.health import calculate_health
from skills.fallow_like.runtime.ingestion import RuntimeIngestion
from skills.fallow_like.runtime.trends import TrendTracker
from skills.fallow_like.analyzers.dead_code import DeadCodeAnalyzer
from skills.fallow_like.analyzers.duplication import DuplicationAnalyzer
from skills.fallow_like.analyzers.complexity import ComplexityAnalyzer
from skills.fallow_like.analyzers.boundaries import BoundaryAnalyzer
from skills.fallow_like.analyzers.feature_flags import FeatureFlagAnalyzer
from skills.fallow_like.analyzers.secrets import SecretsAnalyzer
from skills.fallow_like.analyzers.hot_paths import HotPathAnalyzer
from skills.fallow_like.analyzers.blast_radius import BlastRadiusAnalyzer
from skills.fallow_like.outputs.json_formatter import format as format_json
from skills.fallow_like.outputs.sarif_formatter import format as format_sarif
from skills.fallow_like.outputs.markdown_formatter import format as format_md
from skills.fallow_like.models import AnalysisResult, ProjectStats

app = typer.Typer(
    name="fallow-like",
    help="🔬 Multi-language codebase intelligence engine",
    no_args_is_help=True,
)
console = Console()


def run_analysis(config: FallowConfig) -> AnalysisResult:
    start = time.time()

    scanner = ProjectScanner(str(config.project_root), ignore_patterns=config.ignore_patterns)
    scan = scanner.scan()

    dep_graph = DependencyGraph()
    dep_graph.build(scan)

    runtime = None
    if config.runtime_data_path:
        runtime = RuntimeIngestion.from_json(config.runtime_data_path)

    all_findings = []
    dc = []; dup = []; comp = []; bounds = []; flags = []
    hot = []; blast = []; secs = []

    if config.enable_dead_code:
        dc = DeadCodeAnalyzer(config.dead_code_min_confidence).analyze(scan)
        all_findings.extend(dc)

    if config.enable_duplication:
        dup = DuplicationAnalyzer(config.duplication_min_lines, config.duplication_min_tokens).analyze(scan)
        all_findings.extend(dup)

    if config.enable_complexity:
        comp = ComplexityAnalyzer(config.complexity_threshold).analyze(scan)
        all_findings.extend(comp)

    if config.enable_boundaries:
        bounds = BoundaryAnalyzer().analyze(scan)
        all_findings.extend(bounds)

    if config.enable_feature_flags:
        flags = FeatureFlagAnalyzer().analyze(scan)
        all_findings.extend(flags)

    if config.enable_secrets:
        secs = SecretsAnalyzer().analyze(scan)
        all_findings.extend(secs)

    if config.enable_hot_paths and runtime:
        hot = HotPathAnalyzer(config.hot_path_min_calls).analyze(dep_graph, runtime)
        all_findings.extend(hot)

    if config.enable_blast_radius:
        blast = BlastRadiusAnalyzer(config.blast_radius_max_depth).analyze(dep_graph)
        all_findings.extend(blast)

    result = AnalysisResult(
        project_root=str(config.project_root),
        stats=ProjectStats(
            total_files=scan.stats["total_files"],
            total_lines=scan.stats["total_lines"],
            languages=scan.stats.get("languages", {}),
        ),
        findings=all_findings,
        dead_code=dc, duplication=dup, complexity=comp,
        boundaries=bounds, feature_flags=flags,
        hot_paths=hot, blast_radius=blast, secrets=secs,
        duration_seconds=time.time() - start,
    )

    result.health = calculate_health(result)

    if config.history_db_path:
        tracker = TrendTracker(config.history_db_path)
        tracker.save_snapshot(result.health.score, len(all_findings),
                              {"languages": result.stats.languages})
        trends = tracker.get_trends()
        result.trends = {"score": [t.score for t in trends]}
        alerts = tracker.check_alerts(result.health.score, len(all_findings))
        if alerts:
            console.print("\n[bold red]🚨 Alerts:[/bold red]")
            for a in alerts:
                console.print(f"  [red]• {a.message}[/red]")

    return result


# DEAD CODE (Porthos): def _format_text(result: AnalysisResult) -> str:
    from rich.text import Text
    t = Text()
    t.append("🔬 Fallow-Like Analysis\n\n", style="bold")
    t.append(f"Health: {result.health.score}/100 ({result.health.grade})\n")
    t.append(f"Files: {result.stats.total_files} | Lines: {result.stats.total_lines}\n")
    t.append(f"Findings: {len(result.findings)} | Duration: {result.duration_seconds:.1f}s\n\n")

    sections = [
        ("🔴 Secrets", result.secrets),
        ("❌ Boundaries", result.boundaries),
        ("❌ Complexity", result.complexity),
        ("⚠️ Dead Code", result.dead_code),
        ("⚠️ Duplication", result.duplication),
        ("⚠️ Feature Flags", result.feature_flags),
    ]
    for title, items in sections:
        if items:
            t.append(f"{title}: {len(items)}\n", style="bold")
            for f in items[:10]:
                t.append(f"  • {f.file}:{f.line} — {f.message}\n")
            if len(items) > 10:
                t.append(f"  ... +{len(items)-10} more\n")
    return str(t)


@app.command()
def analyze(
    path: Path = typer.Argument(".", help="Project path"),
    fmt: str = typer.Option("text", "--format", "-f", help="Output: text, json, sarif, markdown"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    runtime: Path | None = typer.Option(None, "--runtime", "-r", help="Runtime data JSON"),
    history: Path | None = typer.Option(None, "--history", help="History DB for trends"),
):
    """Run full analysis on a project."""
    config = FallowConfig(
        project_root=path, output_format=fmt, output_file=output,
        verbose=verbose, runtime_data_path=runtime, history_db_path=history,
    )
    result = run_analysis(config)

    if fmt == "json":
        out = format_json(result)
    elif fmt == "sarif":
        out = format_sarif(result)
    elif fmt == "markdown":
        out = format_md(result)
    else:
        out = _format_text(result)

    if output:
        output.write_text(out)
        console.print(f"[green]✅ Report written to {output}[/green]")
    else:
        print(out)


@app.command()
def health(path: Path = typer.Argument(".", help="Project path")):
    """Quick health check."""
    config = FallowConfig(project_root=path)
    result = run_analysis(config)
    table = Table(title="🏥 Project Health")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Score", f"{result.health.score}/100")
    table.add_row("Grade", result.health.grade)
    table.add_row("Files", str(result.stats.total_files))
    table.add_row("Findings", str(len(result.findings)))
    console.print(table)


@app.command()
def dead_code(path: Path = typer.Argument(".", help="Project path")):
    """Dead code analysis only."""
    config = FallowConfig(
        project_root=path, enable_duplication=False, enable_complexity=False,
        enable_boundaries=False, enable_feature_flags=False, enable_secrets=False,
        enable_hot_paths=False, enable_blast_radius=False,
    )
    result = run_analysis(config)
    console.print(f"\n[bold]Dead Code: {len(result.dead_code)} findings[/bold]")
    for f in result.dead_code:
        console.print(f"  [yellow]• {f.file}:{f.line}[/yellow] — {f.message}")


@app.command()
def secrets(path: Path = typer.Argument(".", help="Project path")):
    """Secrets scan only."""
    config = FallowConfig(
        project_root=path, enable_dead_code=False, enable_duplication=False,
        enable_complexity=False, enable_boundaries=False, enable_feature_flags=False,
        enable_hot_paths=False, enable_blast_radius=False,
    )
    result = run_analysis(config)
    console.print(f"\n[bold]Secrets: {len(result.secrets)} findings[/bold]")
    for f in result.secrets:
        console.print(f"  [red]• {f.file}:{f.line}[/red] — {f.message}")


@app.command()
def trends(
    path: Path = typer.Argument(".", help="Project path"),
    limit: int = typer.Option(30, "--limit", "-n"),
):
    """Show health trends."""
    db_path = Path(path) / ".fallow-history.db"
    if not db_path.exists():
        console.print("[yellow]No history found. Run with --history first.[/yellow]")
        return
    tracker = TrendTracker(db_path)
    points = tracker.get_trends(limit)
    table = Table(title="📈 Health Trends")
    table.add_column("Date", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Findings", style="yellow")
    for p in points:
        table.add_row(p.timestamp[:19], str(p.score), str(p.findings_count))
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()