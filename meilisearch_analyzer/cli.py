"""CLI application for MeiliSearch Analyzer."""

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from meilisearch_analyzer import __version__
from meilisearch_analyzer.core.collector import DataCollector
from meilisearch_analyzer.core.reporter import Reporter
from meilisearch_analyzer.core.scorer import HealthScorer
from meilisearch_analyzer.exporters.json_exporter import JsonExporter
from meilisearch_analyzer.models.finding import FindingSeverity

app = typer.Typer(
    name="meilisearch-analyzer",
    help="Analyze MeiliSearch instances and dumps to identify optimization opportunities.",
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"meilisearch-analyzer version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """MeiliSearch Analyzer - Identify optimization opportunities in your MeiliSearch setup."""
    pass


@app.command()
def analyze(
    url: Annotated[
        Optional[str],
        typer.Option(
            "--url",
            "-u",
            help="MeiliSearch instance URL",
        ),
    ] = None,
    api_key: Annotated[
        Optional[str],
        typer.Option(
            "--api-key",
            "-k",
            help="MeiliSearch API key",
            envvar="MEILI_MASTER_KEY",
        ),
    ] = None,
    dump: Annotated[
        Optional[Path],
        typer.Option(
            "--dump",
            "-d",
            help="Path to MeiliSearch dump file",
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output file path",
        ),
    ] = None,
    format_type: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (json, markdown)",
        ),
    ] = "json",
) -> None:
    """Analyze a MeiliSearch instance or dump file."""
    if not url and not dump:
        console.print("[red]Error:[/red] Either --url or --dump must be provided.")
        raise typer.Exit(1)

    if url and dump:
        console.print("[red]Error:[/red] Cannot specify both --url and --dump.")
        raise typer.Exit(1)

    if dump:
        console.print("[yellow]Dump analysis is not yet implemented.[/yellow]")
        raise typer.Exit(1)

    # Run the async analysis
    # url is guaranteed to be str here due to the check above
    assert url is not None
    asyncio.run(_analyze_instance(url, api_key, output, format_type))


async def _analyze_instance(
    url: str,
    api_key: str | None,
    output: Path | None,
    format_type: str,
) -> None:
    """Analyze a live MeiliSearch instance."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Connect and collect data
        task = progress.add_task("Connecting to MeiliSearch...", total=None)
        collector = DataCollector.from_url(url, api_key)

        if not await collector.collect():
            console.print(f"[red]Error:[/red] Failed to connect to MeiliSearch at {url}")
            await collector.close()
            raise typer.Exit(1)

        progress.update(task, description=f"Connected. Found {len(collector.indexes)} indexes.")

        # Generate report
        progress.update(task, description="Analyzing indexes...")
        reporter = Reporter(collector)
        report = reporter.generate_report(source_url=url)

        await collector.close()

    # Display summary
    _display_summary(report.summary, report.source.meilisearch_version)

    # Display findings
    _display_findings(report)

    # Export report
    if format_type == "json":
        exporter = JsonExporter(pretty=True)
        json_output = exporter.export(report, output)

        if output:
            console.print(f"\n[green]Report saved to:[/green] {output}")
        else:
            console.print("\n[dim]Use --output to save the full report to a file.[/dim]")


def _display_summary(summary, version: str | None) -> None:
    """Display analysis summary."""
    scorer = HealthScorer()
    score_label = scorer.get_score_label(summary.health_score)

    # Build score bar
    filled = int(summary.health_score / 5)
    empty = 20 - filled
    score_bar = "[green]" + "█" * filled + "[/green][dim]░" * empty + "[/dim]"

    summary_text = f"""
[bold]Version:[/bold] {version or 'Unknown'}    [bold]Indexes:[/bold] {summary.total_indexes}    [bold]Documents:[/bold] {summary.total_documents:,}

[bold]Health Score:[/bold] {summary.health_score}/100 ({score_label})
{score_bar}

[red]● Critical:[/red] {summary.critical_issues}    [yellow]● Warnings:[/yellow] {summary.warnings}    [blue]● Suggestions:[/blue] {summary.suggestions}    [dim]● Info:[/dim] {summary.info_count}
"""

    console.print(Panel(summary_text.strip(), title="MeiliSearch Analysis Summary", border_style="blue"))


def _display_findings(report) -> None:
    """Display findings in a table."""
    all_findings = report.get_all_findings()

    if not all_findings:
        console.print("\n[green]No issues found! Your MeiliSearch configuration looks good.[/green]")
        return

    # Filter out info-level findings for display
    display_findings = [f for f in all_findings if f.severity != FindingSeverity.INFO]

    if not display_findings:
        console.print("\n[green]Only informational notes found. No action required.[/green]")
        return

    table = Table(title="\nTop Findings", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", width=12)
    table.add_column("Severity", width=10)
    table.add_column("Index", style="dim", width=15)
    table.add_column("Title", width=40)

    severity_colors = {
        FindingSeverity.CRITICAL: "red",
        FindingSeverity.WARNING: "yellow",
        FindingSeverity.SUGGESTION: "blue",
        FindingSeverity.INFO: "dim",
    }

    # Sort by severity and limit to top 10
    severity_order = {
        FindingSeverity.CRITICAL: 0,
        FindingSeverity.WARNING: 1,
        FindingSeverity.SUGGESTION: 2,
        FindingSeverity.INFO: 3,
    }

    sorted_findings = sorted(
        display_findings,
        key=lambda f: severity_order.get(f.severity, 4),
    )[:10]

    for finding in sorted_findings:
        color = severity_colors.get(finding.severity, "white")
        table.add_row(
            finding.id,
            f"[{color}]{finding.severity.value}[/{color}]",
            finding.index_uid or "global",
            finding.title,
        )

    console.print(table)


@app.command()
def summary(
    url: Annotated[
        str,
        typer.Option(
            "--url",
            "-u",
            help="MeiliSearch instance URL",
        ),
    ],
    api_key: Annotated[
        Optional[str],
        typer.Option(
            "--api-key",
            "-k",
            help="MeiliSearch API key",
            envvar="MEILI_MASTER_KEY",
        ),
    ] = None,
) -> None:
    """Display a quick health summary of a MeiliSearch instance."""
    asyncio.run(_summary_instance(url, api_key))


async def _summary_instance(url: str, api_key: str | None) -> None:
    """Display summary for a live instance."""
    collector = DataCollector.from_url(url, api_key)

    if not await collector.collect():
        console.print(f"[red]Error:[/red] Failed to connect to MeiliSearch at {url}")
        await collector.close()
        raise typer.Exit(1)

    reporter = Reporter(collector)
    report = reporter.generate_report(source_url=url)

    await collector.close()

    _display_summary(report.summary, report.source.meilisearch_version)

    # Show top issues
    critical_findings = [f for f in report.get_all_findings() if f.severity == FindingSeverity.CRITICAL]

    if critical_findings:
        console.print("\n[red bold]Critical Issues:[/red bold]")
        for finding in critical_findings[:3]:
            console.print(f"  • [bold]{finding.index_uid or 'global'}:[/bold] {finding.title}")

    console.print("\n[dim]Run 'analyze' for full report[/dim]")


if __name__ == "__main__":
    app()
