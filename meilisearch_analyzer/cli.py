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
from meilisearch_analyzer.exporters.agent_exporter import AgentExporter
from meilisearch_analyzer.exporters.json_exporter import JsonExporter
from meilisearch_analyzer.exporters.markdown_exporter import MarkdownExporter
from meilisearch_analyzer.exporters.sarif_exporter import SarifExporter
from meilisearch_analyzer.models.finding import FindingSeverity

app = typer.Typer(
    name="meilisearch-analyzer",
    help="Analyze MeiliSearch instances and dumps to identify optimization opportunities.",
    no_args_is_help=True,
)

console = Console()

# Valid output formats
VALID_FORMATS = ("json", "markdown", "sarif", "agent")


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
            help="Output format (json, markdown, sarif, agent)",
        ),
    ] = "json",
    ci_mode: Annotated[
        bool,
        typer.Option(
            "--ci",
            help="CI/CD mode: exit with non-zero code if critical issues found",
        ),
    ] = False,
    fail_on_warnings: Annotated[
        bool,
        typer.Option(
            "--fail-on-warnings",
            help="In CI mode, also fail on warnings (not just critical)",
        ),
    ] = False,
) -> None:
    """Analyze a MeiliSearch instance or dump file."""
    if not url and not dump:
        console.print("[red]Error:[/red] Either --url or --dump must be provided.")
        raise typer.Exit(1)

    if url and dump:
        console.print("[red]Error:[/red] Cannot specify both --url and --dump.")
        raise typer.Exit(1)

    if format_type not in VALID_FORMATS:
        console.print(
            f"[red]Error:[/red] Unknown format '{format_type}'. "
            f"Use one of: {', '.join(VALID_FORMATS)}."
        )
        raise typer.Exit(1)

    if dump:
        exit_code = asyncio.run(_analyze_dump(dump, output, format_type, ci_mode, fail_on_warnings))
    else:
        assert url is not None
        exit_code = asyncio.run(_analyze_instance(url, api_key, output, format_type, ci_mode, fail_on_warnings))

    if exit_code != 0:
        raise typer.Exit(exit_code)


async def _analyze_dump(
    dump_path: Path,
    output: Path | None,
    format_type: str,
    ci_mode: bool,
    fail_on_warnings: bool,
) -> int:
    """Analyze a MeiliSearch dump file."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading dump file...", total=None)
        collector = DataCollector.from_dump(dump_path)

        if not await collector.collect():
            console.print(f"[red]Error:[/red] Failed to parse dump file at {dump_path}")
            await collector.close()
            return 1

        progress.update(task, description=f"Loaded. Found {len(collector.indexes)} indexes.")

        # Generate report
        progress.update(task, description="Analyzing indexes...")
        reporter = Reporter(collector)
        report = reporter.generate_report(source_url=None)
        report.source.type = "dump"
        report.source.dump_path = str(dump_path)

        await collector.close()

    # Display summary
    _display_summary(report.summary, report.source.meilisearch_version)

    # Display findings
    _display_findings(report)

    # Export report
    _export_report(report, output, format_type)

    # CI mode exit code
    return _get_ci_exit_code(report, ci_mode, fail_on_warnings)


async def _analyze_instance(
    url: str,
    api_key: str | None,
    output: Path | None,
    format_type: str,
    ci_mode: bool,
    fail_on_warnings: bool,
) -> int:
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
            return 1

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
    _export_report(report, output, format_type)

    # CI mode exit code
    return _get_ci_exit_code(report, ci_mode, fail_on_warnings)


def _get_ci_exit_code(report, ci_mode: bool, fail_on_warnings: bool) -> int:
    """Determine exit code for CI mode."""
    if not ci_mode:
        return 0

    # Check for critical issues
    if report.summary.critical_issues > 0:
        console.print("\n[red]CI Mode:[/red] Failing due to critical issues.")
        return 2  # Exit code 2 for critical issues

    # Check for warnings if fail_on_warnings is set
    if fail_on_warnings and report.summary.warnings > 0:
        console.print("\n[yellow]CI Mode:[/yellow] Failing due to warnings.")
        return 1  # Exit code 1 for warnings

    console.print("\n[green]CI Mode:[/green] All checks passed.")
    return 0


def _export_report(report, output: Path | None, format_type: str) -> None:
    """Export the report in the specified format."""
    if format_type == "json":
        exporter = JsonExporter(pretty=True)
    elif format_type == "markdown":
        exporter = MarkdownExporter()
    elif format_type == "sarif":
        exporter = SarifExporter()
    elif format_type == "agent":
        exporter = AgentExporter()
    else:
        exporter = JsonExporter(pretty=True)

    exporter.export(report, output)

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


@app.command(name="fix-script")
def fix_script(
    input_file: Annotated[
        Path,
        typer.Option(
            "--input",
            "-i",
            help="Path to analysis JSON file",
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output file path for the fix script",
        ),
    ] = None,
    base_url: Annotated[
        str,
        typer.Option(
            "--url",
            "-u",
            help="MeiliSearch instance URL for fix commands",
        ),
    ] = "http://localhost:7700",
) -> None:
    """Generate a shell script to apply recommended fixes from an analysis file."""
    import orjson

    from meilisearch_analyzer.models.report import AnalysisReport

    if not input_file.exists():
        console.print(f"[red]Error:[/red] Input file not found: {input_file}")
        raise typer.Exit(1)

    try:
        data = orjson.loads(input_file.read_bytes())
        report = AnalysisReport.from_dict(data)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to parse input file: {e}")
        raise typer.Exit(1)

    # Generate fix script
    script_lines = [
        "#!/bin/bash",
        "#",
        "# MeiliSearch Configuration Fix Script",
        "# Generated by MeiliSearch Analyzer",
        "#",
        f"# Based on analysis from: {input_file}",
        "#",
        "",
        "set -e  # Exit on error",
        "",
        f'MEILISEARCH_URL="${{MEILISEARCH_URL:-{base_url}}}"',
        'API_KEY="${MEILI_MASTER_KEY:-YOUR_API_KEY}"',
        "",
        'echo "Applying MeiliSearch configuration fixes..."',
        'echo "Target: $MEILISEARCH_URL"',
        "echo",
        "",
    ]

    # Collect all findings with fixes
    fixable_findings = []
    for index_data in report.indexes.values():
        for finding in index_data.findings:
            if finding.fix:
                fixable_findings.append(finding)

    for finding in report.global_findings:
        if finding.fix:
            fixable_findings.append(finding)

    if not fixable_findings:
        console.print("[yellow]No fixable findings found in the analysis.[/yellow]")
        raise typer.Exit(0)

    for finding in fixable_findings:
        fix = finding.fix
        method = "PATCH"
        endpoint = fix.endpoint

        if endpoint.startswith("PATCH "):
            method = "PATCH"
            endpoint = endpoint[6:]
        elif endpoint.startswith("PUT "):
            method = "PUT"
            endpoint = endpoint[4:]
        elif endpoint.startswith("POST "):
            method = "POST"
            endpoint = endpoint[5:]
        elif endpoint.startswith("DELETE "):
            method = "DELETE"
            endpoint = endpoint[7:]

        payload_json = orjson.dumps(fix.payload, option=orjson.OPT_INDENT_2).decode("utf-8")
        # Escape for heredoc
        payload_escaped = payload_json.replace("'", "'\"'\"'")

        script_lines.extend([
            f"# {finding.id}: {finding.title}",
        ])

        if finding.index_uid:
            script_lines.append(f"# Index: {finding.index_uid}")

        script_lines.extend([
            f'echo "Applying fix: {finding.id} - {finding.title}"',
            f'curl -s -X {method} "$MEILISEARCH_URL{endpoint}" \\',
            "  -H 'Content-Type: application/json' \\",
            '  -H "Authorization: Bearer $API_KEY" \\',
            f"  --data-binary '{payload_escaped}'",
            "echo",
            "",
        ])

    script_lines.extend([
        'echo "All fixes applied successfully!"',
        "",
    ])

    script_content = "\n".join(script_lines)

    if output:
        output.write_text(script_content)
        # Make executable
        output.chmod(0o755)
        console.print(f"[green]Fix script saved to:[/green] {output}")
        console.print(f"[dim]Run with: ./{output}[/dim]")
    else:
        console.print(script_content)


@app.command()
def compare(
    old_report: Annotated[
        Path,
        typer.Argument(
            help="Path to the older/baseline analysis JSON file",
        ),
    ],
    new_report: Annotated[
        Path,
        typer.Argument(
            help="Path to the newer/current analysis JSON file",
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output file path for comparison report",
        ),
    ] = None,
    format_type: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (json, markdown)",
        ),
    ] = "markdown",
) -> None:
    """Compare two analysis reports to detect trends and changes over time."""
    import orjson

    from meilisearch_analyzer.analyzers.historical import HistoricalAnalyzer
    from meilisearch_analyzer.models.comparison import TrendDirection
    from meilisearch_analyzer.models.report import AnalysisReport

    # Validate input files
    if not old_report.exists():
        console.print(f"[red]Error:[/red] Old report file not found: {old_report}")
        raise typer.Exit(1)

    if not new_report.exists():
        console.print(f"[red]Error:[/red] New report file not found: {new_report}")
        raise typer.Exit(1)

    # Load reports
    try:
        old_data = orjson.loads(old_report.read_bytes())
        old = AnalysisReport.from_dict(old_data)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to parse old report: {e}")
        raise typer.Exit(1)

    try:
        new_data = orjson.loads(new_report.read_bytes())
        new = AnalysisReport.from_dict(new_data)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to parse new report: {e}")
        raise typer.Exit(1)

    # Run comparison
    analyzer = HistoricalAnalyzer()
    comparison = analyzer.compare(old, new)

    # Display summary
    _display_comparison_summary(comparison)

    # Export
    if format_type == "json":
        content = orjson.dumps(
            comparison.to_dict(),
            option=orjson.OPT_INDENT_2,
        ).decode("utf-8")
    else:
        content = _format_comparison_markdown(comparison)

    if output:
        output.write_text(content)
        console.print(f"\n[green]Comparison report saved to:[/green] {output}")
    else:
        if format_type == "json":
            console.print(content)


def _display_comparison_summary(comparison) -> None:
    """Display comparison summary in the terminal."""
    from meilisearch_analyzer.models.comparison import TrendDirection

    summary = comparison.summary

    # Trend indicator
    trend_indicators = {
        TrendDirection.UP: "[green]↑ Improving[/green]",
        TrendDirection.DOWN: "[red]↓ Degrading[/red]",
        TrendDirection.STABLE: "[dim]→ Stable[/dim]",
    }
    trend_text = trend_indicators.get(summary.overall_trend, "[dim]→ Stable[/dim]")

    # Health score change
    hs = summary.health_score
    if hs.change > 0:
        hs_change = f"[green]+{hs.change}[/green]"
    elif hs.change < 0:
        hs_change = f"[red]{hs.change}[/red]"
    else:
        hs_change = "[dim]0[/dim]"

    summary_text = f"""
[bold]Time Period:[/bold] {summary.time_between}
[bold]Overall Trend:[/bold] {trend_text}

[bold]Health Score:[/bold] {hs.old_value} → {hs.new_value} ({hs_change})

[bold]Issues:[/bold]
  Critical: {summary.critical_issues.old_value} → {summary.critical_issues.new_value}
  Warnings: {summary.warnings.old_value} → {summary.warnings.new_value}
  Suggestions: {summary.suggestions.old_value} → {summary.suggestions.new_value}

[bold]Indexes:[/bold] {summary.total_indexes.old_value} → {summary.total_indexes.new_value}
  Added: {len(summary.indexes_added) or 'none'}
  Removed: {len(summary.indexes_removed) or 'none'}
  Changed: {len(summary.indexes_changed) or 'none'}
"""

    console.print(Panel(summary_text.strip(), title="Comparison Summary", border_style="blue"))

    # Show improvements
    if summary.improvement_areas:
        console.print("\n[green bold]Improvements:[/green bold]")
        for area in summary.improvement_areas:
            console.print(f"  [green]✓[/green] {area}")

    # Show degradations
    if summary.degradation_areas:
        console.print("\n[red bold]Degradations:[/red bold]")
        for area in summary.degradation_areas:
            console.print(f"  [red]✗[/red] {area}")

    # Show recommendations
    if comparison.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in comparison.recommendations:
            console.print(f"  • {rec}")


def _format_comparison_markdown(comparison) -> str:
    """Format comparison as markdown."""
    from meilisearch_analyzer.models.comparison import ChangeType, TrendDirection

    lines = [
        "# MeiliSearch Analysis Comparison Report",
        "",
        f"**Generated:** {comparison.generated_at.isoformat()}",
        "",
        "## Summary",
        "",
        f"- **Time Between Reports:** {comparison.summary.time_between}",
        f"- **Overall Trend:** {comparison.summary.overall_trend.value.title()}",
        "",
        "### Health Score",
        "",
        f"| Metric | Before | After | Change |",
        f"|--------|--------|-------|--------|",
    ]

    # Add metrics
    for metric_name, metric in [
        ("Health Score", comparison.summary.health_score),
        ("Critical Issues", comparison.summary.critical_issues),
        ("Warnings", comparison.summary.warnings),
        ("Suggestions", comparison.summary.suggestions),
        ("Total Indexes", comparison.summary.total_indexes),
        ("Total Documents", comparison.summary.total_documents),
    ]:
        change_str = f"+{metric.change}" if metric.change > 0 else str(metric.change)
        lines.append(f"| {metric_name} | {metric.old_value} | {metric.new_value} | {change_str} |")

    lines.extend(["", "## Index Changes", ""])

    if comparison.summary.indexes_added:
        lines.append(f"**Added:** {', '.join(comparison.summary.indexes_added)}")
    if comparison.summary.indexes_removed:
        lines.append(f"**Removed:** {', '.join(comparison.summary.indexes_removed)}")
    if comparison.summary.indexes_changed:
        lines.append(f"**Changed:** {', '.join(comparison.summary.indexes_changed)}")

    if not (comparison.summary.indexes_added or comparison.summary.indexes_removed or comparison.summary.indexes_changed):
        lines.append("No index changes detected.")

    # Finding changes
    new_findings = [fc for fc in comparison.finding_changes if fc.change_type == ChangeType.ADDED]
    resolved_findings = [fc for fc in comparison.finding_changes if fc.change_type == ChangeType.REMOVED]

    if new_findings or resolved_findings:
        lines.extend(["", "## Finding Changes", ""])

        if new_findings:
            lines.append("### New Issues")
            lines.append("")
            for fc in new_findings:
                lines.append(f"- **{fc.finding.id}** ({fc.finding.severity.value}): {fc.finding.title}")
                if fc.finding.index_uid:
                    lines.append(f"  - Index: {fc.finding.index_uid}")

        if resolved_findings:
            lines.extend(["", "### Resolved Issues", ""])
            for fc in resolved_findings:
                lines.append(f"- **{fc.finding.id}** ({fc.finding.severity.value}): {fc.finding.title}")

    # Recommendations
    if comparison.recommendations:
        lines.extend(["", "## Recommendations", ""])
        for rec in comparison.recommendations:
            lines.append(f"- {rec}")

    # Improvements and degradations
    if comparison.summary.improvement_areas:
        lines.extend(["", "## Improvements", ""])
        for area in comparison.summary.improvement_areas:
            lines.append(f"- {area}")

    if comparison.summary.degradation_areas:
        lines.extend(["", "## Degradations", ""])
        for area in comparison.summary.degradation_areas:
            lines.append(f"- {area}")

    return "\n".join(lines)


@app.command()
def serve(
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
    host: Annotated[
        str,
        typer.Option(
            "--host",
            "-h",
            help="Host to bind to",
        ),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port to bind to",
        ),
    ] = 8080,
) -> None:
    """Start the web dashboard server."""
    import uvicorn

    from meilisearch_analyzer.web import create_app

    console.print(Panel.fit(
        f"[bold]MeiliSearch Analyzer Dashboard[/bold]\n\n"
        f"URL: [cyan]http://{host}:{port}[/cyan]\n"
        f"Press [bold]Ctrl+C[/bold] to stop",
        border_style="blue",
    ))

    app_instance = create_app(
        meili_url=url,
        meili_api_key=api_key,
        dump_path=dump,
    )

    uvicorn.run(app_instance, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
