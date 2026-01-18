# Meiliscan

A comprehensive tool for analyzing Meilisearch instances and dump files to identify optimization opportunities, potential pitfalls, and provide actionable recommendations.

> **Note**: This is a Go rewrite of the original Python tool. The Python version is archived in `archive/python-v1/` for reference.

## Features

- **Live Instance Analysis**: Connect to a running Meilisearch instance and analyze its configuration
- **Health Scoring**: Get an overall health score for your Meilisearch setup
- **Multiple Export Formats**: JSON and Markdown output
- **CI/CD Integration**: Exit codes for automated pipelines

### Current Findings (MVP)

| ID | Title | Severity | Category |
|----|-------|----------|----------|
| MEILI-S001 | Wildcard searchableAttributes | Critical | Schema |
| MEILI-S002 | ID fields in searchableAttributes | Warning | Schema |
| MEILI-S004 | Empty filterableAttributes | Info | Schema |
| MEILI-S007 | Default ranking rules | Info | Schema |
| MEILI-P004 | Too many indexes | Suggestion | Performance |

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

# Save results to file
meiliscan analyze --url http://localhost:7700 --output analysis.json

# Export as Markdown
meiliscan analyze --url http://localhost:7700 --format markdown --output report.md
```

## CLI Reference

### `analyze`

Analyze a Meilisearch instance.

```bash
meiliscan analyze [flags]
```

**Flags:**
- `--url, -u`: Meilisearch instance URL (required)
- `--api-key, -k`: Meilisearch API key (or set `MEILI_MASTER_KEY` env var)
- `--output, -o`: Output file path
- `--format, -f`: Output format: `json`, `markdown` (default: json)
- `--ci`: CI mode - exit with non-zero code on critical findings

## Development

### Building

```bash
go build -o meiliscan ./cmd/meiliscan
```

### Testing

```bash
go test ./...
```

### Project Structure

```
meiliscan/
├── cmd/meiliscan/          # CLI entry point
├── internal/
│   ├── analyzer/           # Analysis logic (schema, performance)
│   ├── cli/                # Cobra CLI commands
│   ├── collector/          # Data collection (live instance)
│   ├── exporter/           # Output formats (JSON, Markdown)
│   ├── finding/            # Finding model
│   └── report/             # Report model with health scoring
├── docs/                   # Documentation
└── archive/python-v1/      # Archived Python implementation
```

## Roadmap

See [docs/20260118_refactor_mvp/implementation_plan.md](docs/20260118_refactor_mvp/implementation_plan.md) for the full implementation plan.

**Next milestones:**
- Milestone 2: Dump file support
- Milestone 3: Rich CLI output + more findings
- Milestone 4: Web backend (OpenAPI)
- Milestone 5: Web frontend (HTMX + templ)
- Milestone 6: TUI (OpenTUI)

## License

MIT
