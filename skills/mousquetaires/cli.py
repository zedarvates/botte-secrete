"""CLI pour les Quatre Mousquetaires — Multi-Agent Pipeline."""

from __future__ import annotations
import typer
import subprocess
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime

console = Console()

app = typer.Typer(
    name="mousquetaires",
    help="⚔️ Les Quatre Mousquetaires — Multi-Agent Pipeline\n\n"
         "🥊 Porthos (Audit) → ⚔️ d'Artagnan (Fix) → 📿 Aramis (Optimise) → 👑 Athos (Synthèse)",
    no_args_is_help=True,
)

SCRIPTS_DIR = Path(__file__).parent / "scripts"


def run_script(script_name: str, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a Python script from the scripts directory."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        console.print(f"[red]❌ Script not found: {script_path}[/red]")
        raise typer.Exit(1)

    env = {
        "PYTHONPATH": str(Path(__file__).parent.parent.parent),
    }

    return subprocess.run(
        [sys.executable, str(script_path)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**__import__("os").environ, **env},
    )


@app.command()
def audit(
    path: Path = typer.Argument(..., help="Project path to audit"),
    output: Path = typer.Option(None, "--output", "-o", help="Output directory for reports"),
    format: str = typer.Option("both", "--format", "-f", help="Output format: json, md, both"),
):
    """🥊 Porthos — Audit a project (dead code, duplication, complexity, secrets)."""
    console.print(Panel(
        f"[bold]🥊 Porthos — Auditing {path}[/bold]\n"
        f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="blue",
    ))

    if not output:
        output = Path(".")
    output.mkdir(parents=True, exist_ok=True)

    result = run_script("porthos_audit.py", [str(path), str(output)], timeout=120)

    if result.returncode != 0:
        console.print(f"[red]❌ Error: {result.stderr[:500]}[/red]")
        raise typer.Exit(1)

    console.print(result.stdout)

    report_path = output / "audit-report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        _display_audit_summary(report)

    console.print(f"\n[green]✅ Audit complete — Report: {output}/audit-report.json[/green]")


def _display_audit_summary(report: dict):
    """Display audit summary table."""
    console.print(f"\n[bold]📊 Audit Summary[/bold]")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="white")

    table.add_row("Files analyzed", str(report.get("files_analyzed", "?")))
    table.add_row("Total lines", str(report.get("total_lines", "?")))
    table.add_row("Health score", f"{report.get('health_score', '?')}/100 ({report.get('health_grade', '?')})")
    table.add_row("Total findings", str(report.get("findings", {}).get("total", "?")))
    table.add_row("Dead code", str(len(report.get("dead_code", []))))
    table.add_row("Duplications", str(len(report.get("duplication", []))))
    table.add_row("Secrets", str(len(report.get("secrets", []))))
    table.add_row("Boundaries", str(len(report.get("boundaries", []))))

    console.print(table)

    recs = report.get("recommendations", [])
    if recs:
        console.print(f"\n[bold]Recommendations:[/bold]")
        for r in recs:
            console.print(f"  [{r['priority']}] {r['description']}")


@app.command()
def fix(
    path: Path = typer.Argument(..., help="Project path to fix"),
    audit_report: Path = typer.Option(None, "--audit", "-a", help="Audit report to use"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Plan only, don't apply"),
):
    """⚔️ d'Artagnan — Fix bugs from audit report."""
    console.print(Panel(
        f"[bold]⚔️ d'Artagnan — Fixing {path}[/bold]\n"
        f"{'[dim]DRY RUN[/dim]' if dry_run else ''}",
        border_style="green",
    ))

    if not audit_report:
        audit_report = Path("audit-report.json")

    if not audit_report.exists():
        console.print("[red]❌ No audit report found. Run 'audit' first.[/red]")
        raise typer.Exit(1)

    report = json.loads(audit_report.read_text())
    findings = (
        report.get("findings", {}).get("error", []) +
        report.get("findings", {}).get("warning", [])
    )

    console.print(f"Loaded {len(findings)} findings from audit report")

    if dry_run:
        console.print("\n[bold]Planned fixes:[/bold]")
        for f in findings[:20]:
            console.print(f"  • {f.get('file', '?')}:{f.get('line', '?')} — {f.get('description', '?')}")
        return

    result = run_script("dartagnan_fix.py", [str(path), str(audit_report)], timeout=300)

    if result.returncode != 0:
        console.print(f"[red]❌ Error: {result.stderr[:500]}[/red]")
        raise typer.Exit(1)

    console.print(result.stdout)


@app.command()
def optimize(
    path: Path = typer.Argument(..., help="Project path to optimize"),
    output: Path = typer.Option(None, "--output", "-o", help="Output directory"),
):
    """📿 Aramis — Optimize project (tokens, performance, architecture)."""
    console.print(Panel(
        f"[bold]📿 Aramis — Optimizing {path}[/bold]",
        border_style="yellow",
    ))

    if not output:
        output = Path(".")
    output.mkdir(parents=True, exist_ok=True)

    result = run_script("aramis_optimize.py", [str(path), str(output)], timeout=60)

    if result.returncode != 0:
        console.print(f"[red]❌ Error: {result.stderr[:500]}[/red]")
        raise typer.Exit(1)

    console.print(result.stdout)

    plan_path = output / "optimization-plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        stats = plan.get("stats", {})

        table = Table(title="📿 Optimization Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="white")

        table.add_row("Tokens before", f"{stats.get('total_available', 0):,}")
        table.add_row("Tokens after", f"{stats.get('total_loaded', 0):,}")
        table.add_row("Savings", f"{stats.get('savings', 0):,} ({stats.get('savings_percent', 0):.0f}%)")
        table.add_row("Skills loaded", str(len(plan.get("matched_skills", []))))
        table.add_row("Skills excluded", str(len(plan.get("excluded_skills", []))))

        console.print(table)

    console.print(f"\n[green]✅ Optimization complete — Report: {output}/optimization-plan.json[/green]")


@app.command()
def run(
    path: Path = typer.Argument(..., help="Project path"),
    output: Path = typer.Option(None, "--output", "-o", help="Output directory"),
    skip_audit: bool = typer.Option(False, "--skip-audit", help="Skip audit phase"),
    skip_fix: bool = typer.Option(False, "--skip-fix", help="Skip fix phase"),
    skip_optimize: bool = typer.Option(False, "--skip-optimize", help="Skip optimize phase"),
):
    """👑 Athos — Run full pipeline (audit → fix → optimize → synthesis)."""
    console.print(Panel(
        f"[bold]👑 Athos — Full Pipeline for {path}[/bold]\n"
        f"🥊 Porthos → ⚔️ d'Artagnan → 📿 Aramis → 👑 Athos\n"
        f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="red",
    ))

    if not output:
        output = Path("mousquetaires-reports")
    output.mkdir(parents=True, exist_ok=True)

    report = {
        "project": str(path),
        "date": datetime.now().isoformat(),
        "orchestrator": "Athos",
        "phases": {},
    }

    # Phase 1: Audit (Porthos)
    if not skip_audit:
        console.print("\n[bold blue]═══ Phase 1: 🥊 Porthos (Audit) ═══[/bold blue]")
        audit_output = output / "audit"
        audit_output.mkdir(exist_ok=True)
        result = run_script("porthos_audit.py", [str(path), str(audit_output)], timeout=120)
        if result.returncode == 0:
            report["phases"]["audit"] = {"status": "complete", "output": str(audit_output)}
            console.print(result.stdout)
        else:
            report["phases"]["audit"] = {"status": "error", "error": result.stderr[:200]}
            console.print(f"[red]❌ Audit failed: {result.stderr[:200]}[/red]")
    else:
        console.print("\n[dim]═══ Phase 1: 🥊 Porthos (SKIPPED) ═══[/dim]")
        report["phases"]["audit"] = {"status": "skipped"}

    # Phase 2: Fix (d'Artagnan)
    if not skip_fix:
        console.print("\n[bold green]═══ Phase 2: ⚔️ d'Artagnan (Fix) ═══[/bold green]")
        audit_report = output / "audit" / "audit-report.json"
        if audit_report.exists():
            result = run_script("dartagnan_fix.py", [str(path), str(audit_report)], timeout=300)
            if result.returncode == 0:
                report["phases"]["fix"] = {"status": "complete"}
                console.print(result.stdout)
            else:
                report["phases"]["fix"] = {"status": "error", "error": result.stderr[:200]}
        else:
            report["phases"]["fix"] = {"status": "skipped", "reason": "no audit report"}
            console.print("[yellow]⚠ No audit report, skipping fix[/yellow]")
    else:
        console.print("\n[dim]═══ Phase 2: ⚔️ d'Artagnan (SKIPPED) ═══[/dim]")
        report["phases"]["fix"] = {"status": "skipped"}

    # Phase 3: Optimize (Aramis)
    if not skip_optimize:
        console.print("\n[bold yellow]═══ Phase 3: 📿 Aramis (Optimize) ═══[/bold yellow]")
        opt_output = output / "optimize"
        opt_output.mkdir(exist_ok=True)
        result = run_script("aramis_optimize.py", [str(path), str(opt_output)], timeout=60)
        if result.returncode == 0:
            report["phases"]["optimize"] = {"status": "complete"}
            console.print(result.stdout)
        else:
            report["phases"]["optimize"] = {"status": "error", "error": result.stderr[:200]}
    else:
        console.print("\n[dim]═══ Phase 3: 📿 Aramis (SKIPPED) ═══[/dim]")
        report["phases"]["optimize"] = {"status": "skipped"}

    # Phase 4: Synthesis (Athos)
    console.print("\n[bold red]═══ Phase 4: 👑 Athos (Synthesis) ═══[/bold red]")

    consolidated_path = output / "consolidated-report.json"
    with open(consolidated_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    console.print(f"\n[bold green]✅ Pipeline complete![/bold green]")
    console.print(f"📋 Consolidated report: {consolidated_path}")


@app.command()
def status():
    """Show Mousquetaires status and available agents."""
    console.print(Panel(
        "[bold]⚔️ Les Quatre Mousquetaires[/bold]\n\n"
        "🥊 [bold]Porthos[/bold] — L'Auditeur\n"
        "   Audit, dead code, duplication, complexity, secrets\n"
        "   Command: mousquetaires audit <path>\n\n"
        "⚔️ [bold]d'Artagnan[/bold] — Le Développeur\n"
        "   Fix bugs, implement features, write code\n"
        "   Command: mousquetaires fix <path> --audit <report>\n\n"
        "📿 [bold]Aramis[/bold] — L'Optimiseur\n"
        "   Token optimization, performance, architecture\n"
        "   Command: mousquetaires optimize <path>\n\n"
        "👑 [bold]Athos[/bold] — L'Orchestrateur\n"
        "   Coordinate, synthesize, decide\n"
        "   Command: mousquetaires run <path>",
        border_style="red",
    ))


def main():
    app()


if __name__ == "__main__":
    main()