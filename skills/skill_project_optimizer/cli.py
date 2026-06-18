"""CLI for skill-project-optimizer."""

from __future__ import annotations
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from skills.skill_project_optimizer.scanner import scan_skills
from skills.skill_project_optimizer.profiler import profile_project
from skills.skill_project_optimizer.optimizer import optimize_skills, generate_skills_profile

app = typer.Typer(
    name="skill-optimizer",
    help="🧦 Skill Project Optimizer — Reduce token waste by matching skills to projects",
    no_args_is_help=True,
)
console = Console()


@app.command()
def scan(
    skills_dir: str = typer.Option("~/.hermes/skills", "--skills-dir", "-d"),
):
    """Scan all available skills and show stats."""
    result = scan_skills(skills_dir)

    console.print(f"\n[bold]🔬 Skill Scan Results[/bold]")
    console.print(f"Skills directory: {skills_dir}")
    console.print(f"Total skills: {len(result.skills)}")
    console.print(f"Active tokens: {result.active_tokens:,}")
    console.print(f"Archived tokens (waste): {result.archived_tokens:,}")
    console.print(f"Total tokens: {result.total_tokens:,}")

    # Table of skills
    table = Table(title="Skills by Size")
    table.add_column("Tokens", justify="right", style="cyan")
    table.add_column("Lines", justify="right", style="green")
    table.add_column("Category", style="yellow")
    table.add_column("Name", style="white")
    table.add_column("Tags", style="dim")

    for s in result.skills[:30]:
        if s.is_archived:
            continue
        tags = ", ".join(s.tags[:3]) if s.tags else "—"
        table.add_row(
            f"{s.estimated_tokens:,}",
            str(s.size_lines),
            s.category,
            s.name,
            tags,
        )

    console.print(table)

    if result.errors:
        console.print(f"\n[yellow]⚠ {len(result.errors)} errors[/yellow]")
        for e in result.errors[:5]:
            console.print(f"  [dim]{e}[/dim]")


@app.command()
def profile(
    path: Path = typer.Argument(".", help="Project path"),
):
    """Profile a project to determine its characteristics."""
    p = profile_project(str(path))

    console.print(f"\n[bold]📊 Project Profile: {p.name}[/bold]")
    console.print(f"Type: {p.type}")
    console.print(f"Path: {p.path}")
    console.print(f"Files: {p.total_files}")
    console.print(f"Git: {'yes' if p.has_git else 'no'} | GitHub remote: {'yes' if p.has_github_remote else 'no'}")
    console.print(f"Docker: {'yes' if p.has_docker else 'no'} | CI: {'yes' if p.has_ci else 'no'}")
    console.print(f"Package manager: {p.package_manager or 'unknown'}")

    if p.languages:
        console.print(f"\nLanguages:")
        for ext, count in list(p.languages.items())[:8]:
            console.print(f"  {ext}: {count} files")

    if p.frameworks:
        console.print(f"\nFrameworks: {', '.join(p.frameworks)}")

    if p.directories:
        console.print(f"\nDirectories: {', '.join(p.directories[:15])}")


@app.command()
def optimize(
    path: Path = typer.Argument(".", help="Project path"),
    output: Path = typer.Option(None, "--output", "-o", help="Output .skills-profile path"),
    skills_dir: str = typer.Option("~/.hermes/skills", "--skills-dir", "-d"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
):
    """Optimize skills for a project and generate .skills-profile."""
    # Scan all skills
    console.print("[dim]Scanning skills...[/dim]")
    scan_result = scan_skills(skills_dir)

    # Profile project
    console.print(f"[dim]Profiling {path}...[/dim]")
    project = profile_project(str(path))

    # Optimize
    console.print("[dim]Optimizing...[/dim]")
    result = optimize_skills(scan_result, project)

    # Output
    if format == "json":
        import json
        data = {
            "project": {"name": result.profile.name, "type": result.profile.type},
            "matched": [(s.name, p) for s, p in result.matched_skills],
            "excluded": [(s.name, r) for s, r in result.excluded_skills],
            "stats": {
                "total_available": result.total_available_tokens,
                "total_loaded": result.total_loaded_tokens,
                "savings": result.savings_tokens,
                "savings_percent": result.savings_percent,
            },
        }
        console.print_json(data=json.dumps(data, indent=2))
    else:
        console.print(result.summary())

    # Generate profile file
    if not output:
        output = path / ".skills-profile"
    generate_skills_profile(result, output)
    console.print(f"\n[green]✅ .skills-profile written to {output}[/green]")


@app.command()
def compare(
    path: Path = typer.Argument(".", help="Project path"),
    skills_dir: str = typer.Option("~/.hermes/skills", "--skills-dir", "-d"),
):
    """Compare token usage with and without optimization."""
    scan_result = scan_skills(skills_dir)
    project = profile_project(str(path))
    result = optimize_skills(scan_result, project)

    table = Table(title="📊 Token Usage Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Without Optimization", justify="right", style="red")
    table.add_column("With Optimization", justify="right", style="green")
    table.add_column("Savings", justify="right", style="yellow")

    table.add_row(
        "Skills loaded",
        str(len([s for s in scan_result.skills if not s.is_archived])),
        str(len(result.matched_skills)),
        f"-{len(result.excluded_skills)}",
    )
    table.add_row(
        "Tokens loaded",
        f"{result.total_available_tokens:,}",
        f"{result.total_loaded_tokens:,}",
        f"{result.savings_tokens:,}",
    )
    table.add_row(
        "Est. cost per session",
        f"${result.total_available_tokens * 0.000002:.4f}",
        f"${result.total_loaded_tokens * 0.000002:.4f}",
        f"${result.savings_tokens * 0.000002:.4f}",
    )
    table.add_row(
        "Savings",
        "—",
        "—",
        f"{result.savings_percent:.0f}%",
    )

    console.print(table)

    # Recommendations
    console.print(f"\n[bold]Recommendations:[/bold]")
    if result.savings_percent > 50:
        console.print(f"  🟢 High savings potential ({result.savings_percent:.0f}%) — .skills-profile recommended")
    elif result.savings_percent > 20:
        console.print(f"  🟡 Moderate savings ({result.savings_percent:.0f}%) — consider using .skills-profile")
    else:
        console.print(f"  🔵 Low savings ({result.savings_percent:.0f}%) — project uses most available skills")

    # Untagged skills warning
    untagged = [s for s in scan_result.skills if not s.tags and not s.is_archived]
    if untagged:
        console.print(f"\n[yellow]⚠ {len(untagged)} active skills have no tags (not filterable):[/yellow]")
        for s in untagged[:10]:
            console.print(f"  • {s.category}/{s.name} ({s.estimated_tokens:,} tokens)")


@app.command()
def tags(
    skills_dir: str = typer.Option("~/.hermes/skills", "--skills-dir", "-d"),
    missing: bool = typer.Option(False, "--missing", "-m", help="Show only skills without tags"),
):
    """List all skills and their tags."""
    result = scan_skills(skills_dir)

    table = Table(title="🏷 Skills by Tags")
    table.add_column("Skill", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Tags", style="cyan")
    table.add_column("Tokens", justify="right", style="green")

    for s in result.skills:
        if s.is_archived:
            continue
        if missing and s.tags:
            continue
        tags_str = ", ".join(s.tags) if s.tags else "[red]NO TAGS[/red]"
        table.add_row(s.name, s.category, tags_str, f"{s.estimated_tokens:,}")

    console.print(table)


def main():
    app()


if __name__ == "__main__":
    import sys as _sys  # ensure UTF-8 console on Windows (cp1252 crashes on emoji)
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            pass
    main()