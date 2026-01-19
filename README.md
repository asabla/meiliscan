# Meiliscan

A comprehensive static analysis tool for Meilisearch that identifies configuration issues, performance problems, and provides actionable recommendations.

> **Note**: This is a Go rewrite of the original Python tool. The Python version is archived in `archive/python-v1/` for reference.

## Features

- **Live Instance Analysis**: Connect to a running Meilisearch instance and analyze its configuration
- **Dump File Analysis**: Analyze Meilisearch dump files offline
- **Health Scoring**: Get an overall health score (0-100) for your Meilisearch setup
- **51 Findings**: Comprehensive checks across schema, performance, documents, and more
- **Multiple Export Formats**: Terminal, JSON, Markdown, and SARIF output
- **CI/CD Integration**: Exit codes and SARIF format for automated pipelines
- **Search Probes**: Live validation of sort/filter configuration (live instances only)

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/asabla/meiliscan.git
cd meiliscan

# Build
go build -o meiliscan ./cmd/meiliscan

# Or install to $GOPATH/bin
go install ./cmd/meiliscan
```

## Quick Start

### Analyze a Live Instance

```bash
# Basic analysis
meiliscan analyze --url http://localhost:7700

# With API key
meiliscan analyze --url http://localhost:7700 --api-key your-master-key

# Export as JSON
meiliscan analyze --url http://localhost:7700 --format json --output report.json

# Export as Markdown
meiliscan analyze --url http://localhost:7700 --format markdown --output report.md

# Export as SARIF (for GitHub Actions, etc.)
meiliscan analyze --url http://localhost:7700 --format sarif --output results.sarif

# CI mode - exit with non-zero code on critical/warning findings
meiliscan analyze --url http://localhost:7700 --ci
```

### Analyze a Dump File

```bash
# Analyze a Meilisearch dump
meiliscan analyze --dump /path/to/dump.dump
```

## CLI Reference

### `analyze`

Analyze a Meilisearch instance or dump file.

```bash
meiliscan analyze [flags]
```

**Flags:**
| Flag | Short | Description |
|------|-------|-------------|
| `--url` | `-u` | Meilisearch instance URL |
| `--api-key` | `-k` | Meilisearch API key (or set `MEILI_MASTER_KEY` env var) |
| `--dump` | `-d` | Path to Meilisearch dump file |
| `--output` | `-o` | Output file path (default: stdout for terminal) |
| `--format` | `-f` | Output format: `terminal`, `json`, `markdown`, `sarif` (default: terminal) |
| `--ci` | | CI mode - exit code 1 on critical, 2 on warning findings |

### `version`

Show version information.

```bash
meiliscan version
```

## Health Score

Meiliscan calculates a health score from 0-100 based on findings:

| Score | Rating | Description |
|-------|--------|-------------|
| 90-100 | Excellent | No significant issues |
| 70-89 | Good | Minor optimizations possible |
| 50-69 | Fair | Some issues should be addressed |
| 30-49 | Poor | Multiple issues need attention |
| 0-29 | Critical | Serious issues require immediate action |

**Severity weights:**
- Critical: -25 points
- Warning: -10 points  
- Suggestion: -3 points
- Info: -1 point

## Findings Catalog

Meiliscan checks for **51 different findings** across 6 categories:

### Schema (S001-S020)

| ID | Finding | Severity |
|----|---------|----------|
| S001 | Wildcard searchableAttributes | Critical |
| S002 | ID fields in searchableAttributes | Warning |
| S003 | Numeric fields in searchableAttributes | Suggestion |
| S004 | Empty filterableAttributes | Info |
| S005 | Wildcard displayedAttributes with many fields | Suggestion |
| S006 | No stop words configured | Suggestion |
| S007 | Default ranking rules | Info |
| S008 | No distinct attribute configured | Suggestion |
| S009 | Very low pagination limit | Warning |
| S010 | High pagination limit | Suggestion |
| S011 | No primary key defined | Critical |
| S012 | Primary key appears mutable | Warning |
| S013 | No sortable attributes configured | Info |
| S014 | Sortable attribute type issues | Warning |
| S015 | High-cardinality filterable attribute | Suggestion |
| S016 | Faceting maxValuesPerFacet issues | Info/Suggestion |
| S017 | Synonyms configuration issues | Suggestion |
| S018 | Typo tolerance enabled on ID fields | Suggestion |
| S019 | Very permissive typo tolerance | Info |
| S020 | Dictionary/tokenization issues | Suggestion |

### Performance (P001-P010)

| ID | Finding | Severity |
|----|---------|----------|
| P001 | High task failure rate | Critical |
| P002 | Slow indexing operations | Warning |
| P003 | Database fragmentation detected | Suggestion |
| P004 | Too many indexes | Suggestion |
| P005 | Imbalanced index distribution | Info |
| P006 | Too many unique fields | Warning |
| P007 | Sustained task queue backlog | Warning |
| P008 | Many tiny indexing tasks | Suggestion |
| P009 | Oversized indexing tasks | Suggestion |
| P010 | Recurring task failures | Warning |

### Documents (D001-D013)

| ID | Finding | Severity |
|----|---------|----------|
| D001 | Large documents detected | Warning |
| D002 | Inconsistent document schema | Warning |
| D003 | Deep document nesting | Warning |
| D004 | Large array fields detected | Warning |
| D005 | HTML/Markdown content in text fields | Suggestion |
| D006 | High empty/null field ratio | Info |
| D007 | Mixed types in fields | Warning |
| D008 | Very long text fields | Suggestion |
| D009 | Potentially sensitive field names | Warning |
| D010 | Potential PII detected in content | Critical |
| D011 | Arrays of objects in filterable fields | Warning |
| D012 | Geo coordinates not using _geo format | Suggestion |
| D013 | Date strings in sortable attributes | Suggestion |

### Instance (I001)

| ID | Finding | Severity |
|----|---------|----------|
| I001 | Instance running without authentication | Critical |

### Best Practices (B001-B004)

| ID | Finding | Severity |
|----|---------|----------|
| B001 | Settings updated after documents added | Warning |
| B002 | Fields in both searchable and filterable | Suggestion |
| B003 | Unused sortable attributes | Suggestion |
| B004 | Unused filterable attributes | Suggestion |

### Search Probe (Q001-Q003) - Live Only

| ID | Finding | Severity |
|----|---------|----------|
| Q001 | Sort probe failed | Warning |
| Q002 | Filter probe failed | Warning |
| Q003 | Large search response payload | Info |

## CI/CD Integration

### Exit Codes

When using `--ci` flag:
- `0`: No critical or warning findings
- `1`: Critical findings detected
- `2`: Warning findings detected (no critical)

### GitHub Actions Example

```yaml
name: Meilisearch Analysis

on: [push, pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      
      - name: Install Meiliscan
        run: go install github.com/asabla/meiliscan/cmd/meiliscan@latest
      
      - name: Analyze Meilisearch
        run: |
          meiliscan analyze \
            --url ${{ secrets.MEILI_URL }} \
            --api-key ${{ secrets.MEILI_KEY }} \
            --format sarif \
            --output results.sarif \
            --ci
      
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: results.sarif
```

## Development

### Building

```bash
go build -o meiliscan ./cmd/meiliscan
```

### Testing

```bash
# Run all tests
go test ./...

# With coverage
go test -cover ./...

# Verbose output
go test -v ./...
```

### Project Structure

```
meiliscan/
├── cmd/meiliscan/          # CLI entry point
├── internal/
│   ├── analyzer/           # Analysis logic
│   │   ├── schema.go       # S001-S020 findings
│   │   ├── performance.go  # P001-P010 findings
│   │   ├── documents.go    # D001-D013 findings
│   │   ├── instance.go     # I001 finding
│   │   ├── best_practices.go # B001-B004 findings
│   │   └── search_probe.go # Q001-Q003 findings
│   ├── cli/                # Cobra CLI commands
│   ├── collector/          # Data collection (live/dump)
│   ├── exporter/           # Output formats
│   ├── finding/            # Finding model
│   └── report/             # Report model with health scoring
├── api/                    # HTTP API (future)
├── web/                    # Web UI (future)
└── archive/python-v1/      # Archived Python implementation
```

## Roadmap

**Completed:**
- Live instance analysis
- Dump file analysis  
- 51 findings across 6 categories
- JSON, Markdown, SARIF export
- CI/CD integration
- Health scoring

**Planned:**
- Web UI with HTMX
- TUI mode
- Watch mode for continuous monitoring
- Diff reports between analyses

## License

MIT
