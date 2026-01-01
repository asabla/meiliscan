# MeiliSearch Analyzer

A comprehensive tool for analyzing MeiliSearch instances and dump files to identify optimization opportunities, potential pitfalls, and provide actionable recommendations.

## Features

- **Live Instance Analysis**: Connect to a running MeiliSearch instance and analyze its configuration
- **Dump File Analysis**: Parse and analyze MeiliSearch dump archives without a running instance
- **28 Finding Types**: Comprehensive checks across schema, documents, performance, and best practices
- **Health Scoring**: Get an overall health score for your MeiliSearch setup
- **Web Dashboard**: Interactive web UI for exploring analysis results
- **Historical Comparison**: Compare two analysis reports to track changes over time
- **Multiple Export Formats**: JSON, Markdown, SARIF (for GitHub/IDEs), and Agent-friendly output
- **CI/CD Integration**: Exit codes and flags for automated pipelines
- **Fix Script Generation**: Generate executable scripts to apply recommended fixes

## Installation

### Using uvx (Recommended)

```bash
uvx meilisearch-analyzer --help
```

### Using pip

```bash
pip install meilisearch-analyzer
```

### From source

```bash
git clone https://github.com/yourusername/meilisearch-analyzer.git
cd meilisearch-analyzer
uv sync
```

## Quick Start

### Analyze a Live Instance

```bash
# Basic analysis
meilisearch-analyzer analyze --url http://localhost:7700

# With API key
meilisearch-analyzer analyze --url http://localhost:7700 --api-key your-master-key

# Save results to file
meilisearch-analyzer analyze --url http://localhost:7700 --output analysis.json
```

### Analyze a Dump File

```bash
# Analyze a dump archive
meilisearch-analyzer analyze --dump ./path/to/dump.dump

# Export as markdown
meilisearch-analyzer analyze --dump ./dump.dump --format markdown --output report.md
```

### Web Dashboard

```bash
# Start the web dashboard
meilisearch-analyzer serve --url http://localhost:7700 --port 8080

# Then open http://localhost:8080 in your browser
```

### Quick Health Summary

```bash
meilisearch-analyzer summary --url http://localhost:7700
```

## Example Output

```
+---------------------------------------------------------------------+
|                    MeiliSearch Analysis Summary                      |
+---------------------------------------------------------------------+
|  Version: 1.12.0    Indexes: 5    Documents: 125,000                |
|                                                                      |
|  Health Score: 72/100 (Needs Attention)                              |
|  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░                            |
|                                                                      |
|  * Critical: 2    * Warnings: 8    * Suggestions: 15                 |
+---------------------------------------------------------------------+

                           Top Findings
+-------------+-----------+-----------------+------------------------+
| ID          | Severity  | Index           | Title                  |
+-------------+-----------+-----------------+------------------------+
| MEILI-S001  | critical  | products        | Wildcard searchable... |
| MEILI-S002  | warning   | orders          | ID fields in search... |
+-------------+-----------+-----------------+------------------------+
```

## Analysis Checks

### Schema Findings (S001-S010)

| ID | Title | Severity | Description |
|----|-------|----------|-------------|
| MEILI-S001 | Wildcard searchableAttributes | Critical | All fields are searchable, including IDs and numbers |
| MEILI-S002 | ID fields in searchableAttributes | Warning | ID fields shouldn't typically be searchable |
| MEILI-S003 | Numeric fields in searchableAttributes | Suggestion | Numeric fields may be better as filterable |
| MEILI-S004 | Empty filterableAttributes | Info | No filterable attributes configured |
| MEILI-S005 | Wildcard displayedAttributes with many fields | Suggestion | Large response payloads |
| MEILI-S006 | No stop words configured | Suggestion | Missing language-appropriate stop words |
| MEILI-S007 | Default ranking rules | Info | Using default ranking rules |
| MEILI-S008 | No distinct attribute set | Suggestion | Potentially duplicate results |
| MEILI-S009 | Very low pagination limit | Warning | maxTotalHits < 100 |
| MEILI-S010 | High pagination limit | Suggestion | maxTotalHits > 10000 |

### Document Findings (D001-D008)

| ID | Title | Severity | Description |
|----|-------|----------|-------------|
| MEILI-D001 | Large documents | Warning | Documents exceed recommended size |
| MEILI-D002 | Inconsistent schema | Warning | Field presence varies across documents |
| MEILI-D003 | Deep nesting | Warning | Deeply nested object structures |
| MEILI-D004 | Large arrays | Warning | Arrays with many elements |
| MEILI-D005 | HTML in text fields | Suggestion | Raw HTML in searchable content |
| MEILI-D006 | Empty field values | Info | Fields with empty or null values |
| MEILI-D007 | Mixed types in field | Warning | Same field has different types |
| MEILI-D008 | Very long text | Suggestion | Text fields exceeding optimal length |

### Performance Findings (P001-P006)

| ID | Title | Severity | Description |
|----|-------|----------|-------------|
| MEILI-P001 | High task failure rate | Critical | Many indexing tasks are failing |
| MEILI-P002 | Slow indexing | Warning | Indexing performance is degraded |
| MEILI-P003 | Database fragmentation | Suggestion | Database may benefit from optimization |
| MEILI-P004 | Too many indexes | Suggestion | Large number of indexes may impact performance |
| MEILI-P005 | Imbalanced indexes | Info | Document counts vary significantly |
| MEILI-P006 | Too many fields | Warning | Indexes have excessive field counts |

### Best Practices Findings (B001-B004)

| ID | Title | Severity | Description |
|----|-------|----------|-------------|
| MEILI-B001 | Settings after documents | Warning | Settings were updated after adding documents |
| MEILI-B002 | Duplicate searchable/filterable | Suggestion | Same fields in both searchable and filterable |
| MEILI-B003 | Missing embedders config | Info | No AI/vector search configuration |
| MEILI-B004 | Old MeiliSearch version | Suggestion/Warning | Running an outdated version |

## CLI Reference

### `analyze`

Analyze a MeiliSearch instance or dump file.

```bash
meilisearch-analyzer analyze [OPTIONS]
```

Options:
- `--url, -u`: MeiliSearch instance URL
- `--api-key, -k`: MeiliSearch API key (or set `MEILI_MASTER_KEY` env var)
- `--dump, -d`: Path to a MeiliSearch dump file
- `--output, -o`: Output file path
- `--format, -f`: Output format: `json`, `markdown`, `sarif`, `agent` (default: json)
- `--ci`: CI mode - exit with non-zero code on findings
- `--fail-on-warnings`: In CI mode, also fail on warnings (not just critical)

### `compare`

Compare two analysis reports to track changes over time.

```bash
meilisearch-analyzer compare OLD_REPORT NEW_REPORT [OPTIONS]
```

Options:
- `--output, -o`: Output file path
- `--format, -f`: Output format: `json`, `markdown` (default: markdown)

### `fix-script`

Generate a shell script to apply recommended fixes.

```bash
meilisearch-analyzer fix-script --input REPORT_JSON --output SCRIPT_PATH
```

Options:
- `--input, -i`: Path to analysis JSON report
- `--output, -o`: Output script path

### `serve`

Start the web dashboard.

```bash
meilisearch-analyzer serve [OPTIONS]
```

Options:
- `--url, -u`: MeiliSearch instance URL
- `--api-key, -k`: MeiliSearch API key
- `--host`: Dashboard host (default: 127.0.0.1)
- `--port, -p`: Dashboard port (default: 8080)

### `summary`

Display a quick health summary.

```bash
meilisearch-analyzer summary [OPTIONS]
```

Options:
- `--url, -u`: MeiliSearch instance URL (required)
- `--api-key, -k`: MeiliSearch API key

## Export Formats

### JSON (default)

Structured JSON output for programmatic processing.

```bash
meilisearch-analyzer analyze --url ... --format json --output report.json
```

### Markdown

Human-readable report with tables and formatted findings.

```bash
meilisearch-analyzer analyze --url ... --format markdown --output report.md
```

### SARIF

Static Analysis Results Interchange Format for GitHub Code Scanning and IDE integration.

```bash
meilisearch-analyzer analyze --url ... --format sarif --output results.sarif
```

### Agent

Optimized output for AI coding agents (Claude, GPT, etc.) with prioritized issues and fix commands.

```bash
meilisearch-analyzer analyze --url ... --format agent --output agent-context.md
```

## CI/CD Integration

Use the `--ci` flag to enable CI mode with appropriate exit codes:

```bash
# Exit code 2 on critical findings, 0 otherwise
meilisearch-analyzer analyze --url http://localhost:7700 --ci

# Exit code 1 on warnings, 2 on critical findings
meilisearch-analyzer analyze --url http://localhost:7700 --ci --fail-on-warnings
```

### GitHub Actions Example

```yaml
- name: Analyze MeiliSearch
  run: |
    meilisearch-analyzer analyze \
      --url ${{ secrets.MEILISEARCH_URL }} \
      --api-key ${{ secrets.MEILISEARCH_API_KEY }} \
      --format sarif \
      --output results.sarif \
      --ci

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v2
  with:
    sarif_file: results.sarif
```

## Web Dashboard

The web dashboard provides an interactive interface for exploring analysis results:

- **Dashboard Overview**: Health score gauge, summary statistics, quick actions
- **Index Details**: Per-index settings, statistics, and findings
- **Findings Explorer**: Filter by severity, category, and index
- **Comparison View**: Upload and compare two JSON reports
- **Document Sampling**: Preview sample documents from each index

Start the dashboard:

```bash
meilisearch-analyzer serve --url http://localhost:7700 --port 8080
```

## Development

### Setup

```bash
git clone https://github.com/yourusername/meilisearch-analyzer.git
cd meilisearch-analyzer
uv sync --all-extras
```

### Running Tests

```bash
uv run pytest
```

### Running with Coverage

```bash
uv run pytest --cov=meilisearch_analyzer --cov-report=html
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
