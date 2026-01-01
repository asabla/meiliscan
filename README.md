# MeiliSearch Analyzer

A comprehensive tool for analyzing MeiliSearch instances to identify optimization opportunities, potential pitfalls, and provide actionable recommendations.

## Features

- **Live Instance Analysis**: Connect to a running MeiliSearch instance and analyze its configuration
- **Schema Analysis**: Detect issues with searchable, filterable, and sortable attributes
- **Health Scoring**: Get an overall health score for your MeiliSearch setup
- **Actionable Recommendations**: Receive specific fixes with API endpoints and payloads
- **JSON Export**: Export analysis results for further processing or integration with other tools

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

### Quick Health Summary

```bash
meilisearch-analyzer summary --url http://localhost:7700
```

## Example Output

```
╭─────────────────────────────────────────────────────────────────╮
│                    MeiliSearch Analysis Summary                  │
├─────────────────────────────────────────────────────────────────┤
│  Version: 1.12.0    Indexes: 5    Documents: 125,000            │
│                                                                 │
│  Health Score: 72/100 (Needs Attention)                         │
│  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░                       │
│                                                                 │
│  ● Critical: 2    ● Warnings: 8    ● Suggestions: 15            │
╰─────────────────────────────────────────────────────────────────╯

                           Top Findings
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
┃ ID           ┃ Severity   ┃ Index           ┃ Title              ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ MEILI-S001   │ critical   │ products        │ Wildcard search... │
│ MEILI-S002   │ warning    │ orders          │ ID fields in se... │
└──────────────┴────────────┴─────────────────┴────────────────────┘
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

## CLI Reference

### `analyze`

Analyze a MeiliSearch instance.

```bash
meilisearch-analyzer analyze [OPTIONS]
```

Options:
- `--url, -u`: MeiliSearch instance URL
- `--api-key, -k`: MeiliSearch API key (or set `MEILI_MASTER_KEY` env var)
- `--output, -o`: Output file path
- `--format, -f`: Output format (json, markdown) - default: json

### `summary`

Display a quick health summary.

```bash
meilisearch-analyzer summary [OPTIONS]
```

Options:
- `--url, -u`: MeiliSearch instance URL (required)
- `--api-key, -k`: MeiliSearch API key

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

## Roadmap

- [x] **Phase 1**: Core Analysis (MVP)
  - [x] CLI with analyze command
  - [x] Live instance collector
  - [x] Schema analyzer (S001-S010)
  - [x] JSON export
  - [x] Health scoring

- [ ] **Phase 2**: Dump Support & Documents
  - [ ] Dump file parser
  - [ ] Document analyzer (D001-D008)
  - [ ] Performance analyzer (P001-P006)
  - [ ] Markdown export

- [ ] **Phase 3**: Web Dashboard
  - [ ] FastAPI application
  - [ ] Dashboard overview
  - [ ] Index detail views

- [ ] **Phase 4**: Advanced Features
  - [ ] SARIF export
  - [ ] Agent-friendly export
  - [ ] Fix script generation

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
