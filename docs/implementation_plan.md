# MeiliSearch Analyzer Tool - Technical Specification

## Implementation Status

> **Status: All Phases Complete**
>
> All phases have been fully implemented. The tool is production-ready with:
> - Live instance analysis via API
> - Dump file parsing (.dump archives)
> - Web dashboard (FastAPI + Jinja2)
> - Multiple export formats (JSON, Markdown, SARIF, Agent)
> - CI/CD integration mode
> - Fix script generation
> - All 28 finding types (S001-S010, D001-D008, P001-P006, B001-B004)
>
> **Remaining Future Work:** Historical Analysis (comparing dumps over time)

---

## Executive Summary

This document outlines the design for **MeiliSearch Analyzer** - a comprehensive
tool for analyzing MeiliSearch instances and dumps to identify optimization
opportunities, potential pitfalls, and provide actionable recommendations. The
tool supports both live instance connections and offline dump analysis, with
results exportable in formats suitable for coding agents.

---

## 1. Chosen Tech Stack

### Primary Language: **Python**

**Rationale:**
- **Easy distribution**: Runs via `uvx meilisearch-analyzer` (using uv/uvx) or Docker
- **Rich ecosystem**: Excellent libraries for HTTP APIs, data analysis, and web frameworks
- **MeiliSearch SDK**: Official `meilisearch` Python SDK available
- **Data analysis**: pandas, numpy for statistical analysis
- **Web UI**: FastAPI + HTMX for lightweight interactive dashboard

### Core Dependencies

```toml
[project]
name = "meilisearch-analyzer"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "meilisearch>=0.31.0",        # Official MeiliSearch Python SDK
    "httpx>=0.27.0",              # Async HTTP client
    "fastapi>=0.115.0",           # Web framework for dashboard
    "uvicorn>=0.32.0",            # ASGI server
    "jinja2>=3.1.0",              # HTML templating
    "pydantic>=2.0",              # Data validation
    "rich>=13.0",                 # CLI output formatting
    "typer>=0.12.0",              # CLI framework
    "orjson>=3.10.0",             # Fast JSON parsing (for large dumps)
    "pandas>=2.2.0",              # Data analysis
    "python-multipart>=0.0.9",    # File upload handling
]

[project.scripts]
meilisearch-analyzer = "meilisearch_analyzer.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Distribution Methods

1. **uvx (Recommended)**
   ```bash
   uvx meilisearch-analyzer --url http://localhost:7700 --api-key xxx
   uvx meilisearch-analyzer --dump ./dump-20240101.dump
   ```

2. **Docker**
   ```bash
   docker run -p 8080:8080 meilisearch-analyzer \
     --url http://host.docker.internal:7700
   ```

3. **pip/pipx**
   ```bash
   pipx install meilisearch-analyzer
   ```

---

## 2. Analysis Methodology

### 2.1 Data Collection Sources

#### A. Live Instance Analysis

Connect to a running MeiliSearch instance and collect data via API:

| Endpoint | Data Collected |
|----------|----------------|
| `GET /indexes` | List of all indexes with metadata |
| `GET /indexes/{uid}/settings` | Complete settings for each index |
| `GET /indexes/{uid}/stats` | Document count, field distribution |
| `GET /stats` | Global database size, last update |
| `GET /health` | Instance health status |
| `GET /version` | MeiliSearch version |
| `GET /tasks?limit=1000` | Recent task history (for performance analysis) |
| `GET /metrics` (if enabled) | Prometheus metrics |

#### B. Dump Analysis

Parse MeiliSearch dump files (`.dump` format - compressed archive):

**Dump Structure:**
```
dump-{timestamp}/
├── metadata.json           # Version, dump date, instance UID
├── keys.json              # API keys (if present)
├── tasks/
│   └── queue.json         # Task history
└── indexes/
    └── {index_uid}/
        ├── metadata.json  # Index metadata, primary key
        ├── settings.json  # Complete index settings
        └── documents.jsonl # All documents (NDJSON format)
```

### 2.2 Analysis Categories

#### Category 1: Schema & Settings Analysis

| Check | What We Analyze | Pitfall Detected |
|-------|-----------------|------------------|
| Searchable Attributes | Is `["*"]` being used? | All fields indexed = slower search |
| Filterable Attributes | Fields configured vs. fields used | Unused filterable fields waste index space |
| Sortable Attributes | Fields configured | Over-configuration increases index size |
| Displayed Attributes | `["*"]` vs explicit list | Large docs returned unnecessarily |
| Ranking Rules | Default vs custom | Missing custom ranking for use case |
| Stop Words | Language-appropriate stops | Missing stops = poor relevancy |
| Synonyms | Configured synonyms | Missing common synonyms |
| Distinct Attribute | Set vs. unset | Duplicate results possible |
| Typo Tolerance | Settings per attribute | Too permissive = irrelevant results |

#### Category 2: Document Analysis

| Check | What We Analyze | Pitfall Detected |
|-------|-----------------|------------------|
| Document Size | Average/max document size | Large documents slow indexing |
| Field Distribution | Fields per document | Inconsistent schemas |
| Nested Objects | Depth of nesting | Deep nesting = flattening issues |
| Array Fields | Array sizes | Large arrays slow filtering |
| Primary Key | Type and pattern | Non-optimal key format |
| Field Types | Type consistency | Mixed types in same field |
| Empty Fields | Null/empty field ratio | Wasted storage |
| HTML/Markdown Content | Raw markup in fields | Should be stripped before indexing |

#### Category 3: Performance Indicators

| Check | What We Analyze | Pitfall Detected |
|-------|-----------------|------------------|
| Index Size | Size vs document count ratio | Bloated index |
| Field Count | Total unique fields | Too many fields (>100) |
| Task History | Failed tasks, duration trends | Recurring indexing issues |
| DB Size vs Used Size | Gap between total/used | Fragmentation opportunity |
| Document Count | Per index distribution | Imbalanced indexes |

#### Category 4: Best Practices Compliance

| Check | Best Practice | Status |
|-------|--------------|--------|
| Settings Before Documents | Settings should be configured first | Check task order |
| Searchable ≠ Filterable | Don't duplicate unless needed | Cross-reference |
| ID Fields | IDs shouldn't be searchable | Check searchableAttributes |
| Pagination Limits | maxTotalHits configuration | Default 1000 may be too low/high |
| Faceting Limits | maxValuesPerFacet setting | May need tuning |

### 2.3 Analysis Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYSIS PIPELINE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │ Data Source  │────▶│  Collector   │────▶│   Analyzer   │    │
│  │              │     │              │     │              │    │
│  │ • Live API   │     │ • Fetch all  │     │ • Schema     │    │
│  │ • Dump file  │     │   indexes    │     │ • Documents  │    │
│  │              │     │ • Settings   │     │ • Performance│    │
│  │              │     │ • Stats      │     │ • Best Pract.│    │
│  │              │     │ • Documents  │     │              │    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│                                                   │             │
│                                                   ▼             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │   Export     │◀────│   Scoring    │◀────│   Findings   │    │
│  │              │     │              │     │              │    │
│  │ • JSON       │     │ • Severity   │     │ • Issues     │    │
│  │ • Markdown   │     │ • Impact     │     │ • Warnings   │    │
│  │ • Dashboard  │     │ • Priority   │     │ • Suggestions│    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Analysis Result Structure

### 3.1 Output Schema (JSON)

The primary export format is structured JSON, designed for consumption by coding agents:

```json
{
  "$schema": "https://meilisearch-analyzer.dev/schema/v1.json",
  "version": "1.0.0",
  "generated_at": "2025-01-15T10:30:00Z",
  "source": {
    "type": "instance|dump",
    "url": "http://localhost:7700",
    "meilisearch_version": "1.12.0",
    "dump_date": null
  },
  "summary": {
    "total_indexes": 5,
    "total_documents": 1250000,
    "database_size_bytes": 4294967296,
    "health_score": 72,
    "critical_issues": 2,
    "warnings": 8,
    "suggestions": 15
  },
  "indexes": {
    "products": {
      "metadata": {
        "primary_key": "id",
        "created_at": "2024-06-15T08:00:00Z",
        "updated_at": "2025-01-14T23:45:00Z",
        "document_count": 500000
      },
      "settings": {
        "current": { /* full current settings */ },
        "recommended": { /* recommended settings */ },
        "diff": [ /* structured diff */ ]
      },
      "statistics": {
        "field_distribution": {
          "id": 500000,
          "title": 500000,
          "description": 498500,
          "price": 500000,
          "category": 500000,
          "tags": 450000
        },
        "avg_document_size_bytes": 2048,
        "max_document_size_bytes": 15000,
        "field_type_analysis": {
          "id": {"types": ["string"], "samples": ["prod_12345"]},
          "price": {"types": ["number"], "min": 0.99, "max": 9999.99},
          "tags": {"types": ["array"], "avg_length": 4.2}
        }
      },
      "findings": [
        {
          "id": "MEILI-001",
          "category": "schema",
          "severity": "critical",
          "title": "All fields are searchable (wildcard)",
          "description": "searchableAttributes is set to ['*'], causing all fields including IDs and numbers to be indexed for search.",
          "impact": "Increased index size, slower indexing, potentially irrelevant search results",
          "current_value": ["*"],
          "recommended_value": ["title", "description", "category"],
          "fix": {
            "type": "settings_update",
            "endpoint": "PATCH /indexes/products/settings",
            "payload": {
              "searchableAttributes": ["title", "description", "category"]
            }
          },
          "references": [
            "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
          ]
        }
      ]
    }
  },
  "global_findings": [
    {
      "id": "MEILI-G001",
      "category": "performance",
      "severity": "warning",
      "title": "Database fragmentation detected",
      "description": "Gap between db_size and used_db_size suggests 40% fragmentation",
      "impact": "Increased disk usage",
      "recommendation": "Consider creating a dump and re-importing"
    }
  ],
  "action_plan": {
    "priority_order": ["MEILI-001", "MEILI-003", "MEILI-G001"],
    "estimated_impact": {
      "index_size_reduction": "~35%",
      "indexing_speed_improvement": "~25%",
      "search_latency_improvement": "~15%"
    }
  }
}
```

### 3.2 Finding Severity Levels

| Level | Color | Description | Action Required |
|-------|-------|-------------|-----------------|
| `critical` | 🔴 Red | Significant performance/correctness issue | Immediate fix recommended |
| `warning` | 🟡 Yellow | Suboptimal configuration | Should address soon |
| `suggestion` | 🔵 Blue | Optimization opportunity | Consider when convenient |
| `info` | ⚪ Gray | Informational note | No action needed |

### 3.3 Finding Categories

- `schema` - Settings and index configuration issues
- `documents` - Document structure and content issues
- `performance` - Indexing/search performance concerns
- `best_practices` - Deviation from recommended patterns
- `security` - API key or access configuration concerns

### 3.4 Export Formats

#### A. JSON (Primary - for coding agents)
```bash
meilisearch-analyzer analyze --output analysis.json
```

#### B. Markdown Report
```bash
meilisearch-analyzer analyze --format markdown --output report.md
```

#### C. SARIF (Static Analysis Results Interchange Format)
For integration with code review tools:
```bash
meilisearch-analyzer analyze --format sarif --output results.sarif
```

#### D. Claude/AI Agent Format
Structured prompt-ready format:
```bash
meilisearch-analyzer analyze --format agent --output agent-context.md
```

Example agent format output:
```markdown
# MeiliSearch Analysis Context

## Current State Summary
- 5 indexes, 1.25M documents, 4GB database
- Health score: 72/100 (needs attention)

## Critical Issues (Fix First)

### Issue MEILI-001: Wildcard Searchable Attributes
**Index:** products
**Problem:** All fields are searchable, including IDs and numbers
**Current:** `searchableAttributes: ["*"]`
**Recommended:** `searchableAttributes: ["title", "description", "category"]`

**Fix Command:**
```bash
curl -X PATCH 'http://localhost:7700/indexes/products/settings' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  --data-binary '{"searchableAttributes": ["title", "description", "category"]}'
```

[... additional issues ...]
```

---

## 4. Tool Architecture

### 4.1 Module Structure

> **Implementation Note:** The actual structure differs slightly from the spec.
> The `static/` directory was not created; CSS is embedded in templates.

```
meilisearch_analyzer/
├── __init__.py
├── cli.py                      # Typer CLI application
├── core/
│   ├── __init__.py
│   ├── collector.py            # Data collection from API/dump
│   ├── analyzer.py             # Analysis engine
│   ├── scorer.py               # Health score calculation
│   └── reporter.py             # Report generation
├── collectors/
│   ├── __init__.py
│   ├── base.py                 # Base collector class
│   ├── live_instance.py        # Live API collector
│   └── dump_parser.py          # Dump file parser
├── analyzers/
│   ├── __init__.py
│   ├── base.py                 # Base analyzer class
│   ├── schema_analyzer.py      # Settings analysis (S001-S010) ✓
│   ├── document_analyzer.py    # Document structure analysis (D001-D008) ✓
│   ├── performance_analyzer.py # Performance metrics (P001-P006) ✓
│   └── best_practices.py       # Best practices checks (B001-B004) ✓
├── models/
│   ├── __init__.py
│   ├── index.py               # Index data models
│   ├── finding.py             # Finding/issue models
│   └── report.py              # Report models
├── exporters/
│   ├── __init__.py
│   ├── base.py                # Base exporter class
│   ├── json_exporter.py       # JSON export
│   ├── markdown_exporter.py   # Markdown report
│   ├── sarif_exporter.py      # SARIF format
│   └── agent_exporter.py      # AI agent format
└── web/
    ├── __init__.py
    ├── app.py                 # FastAPI application
    ├── routes.py              # API routes
    └── templates/             # Jinja2 templates (CSS inline)
        ├── base.html
        ├── dashboard.html
        ├── index_detail.html
        ├── findings.html
        └── components/
            └── finding_detail.html
```

### 4.2 CLI Interface

```bash
# Analyze live instance
meilisearch-analyzer analyze \
  --url http://localhost:7700 \
  --api-key "your-master-key" \
  --output analysis.json

# Analyze dump file
meilisearch-analyzer analyze \
  --dump ./dumps/20250115-dump.dump \
  --output analysis.json

# Start web dashboard
meilisearch-analyzer serve \
  --url http://localhost:7700 \
  --port 8080

# Upload dump to web interface
meilisearch-analyzer serve \
  --upload-enabled \
  --port 8080

# Quick summary (stdout)
meilisearch-analyzer summary \
  --url http://localhost:7700

# Generate fix script
meilisearch-analyzer fix-script \
  --input analysis.json \
  --output apply-fixes.sh
```

### 4.3 Web Dashboard Features

The web UI provides an interactive exploration experience:

1. **Dashboard Overview**
   - Health score gauge
   - Index cards with key metrics
   - Findings summary by severity
   - Quick actions

2. **Index Detail View**
   - Settings comparison (current vs recommended)
   - Field distribution chart
   - Document sampling (random documents for inspection)
   - Per-index findings

3. **Findings Explorer**
   - Filter by severity/category/index
   - Detailed explanation for each finding
   - One-click copy for fix commands
   - Bulk export selected findings

4. **Interactive Analysis**
   - Upload dump file
   - Connect to instance URL
   - Refresh data
   - Export results

---

## 5. Complete Finding Catalog

### 5.1 Schema Findings

| ID | Title | Severity | Detection |
|----|-------|----------|-----------|
| MEILI-S001 | Wildcard searchableAttributes | Critical | `searchableAttributes == ["*"]` |
| MEILI-S002 | ID fields in searchableAttributes | Warning | Field names containing "id", "_id" |
| MEILI-S003 | Numeric fields in searchableAttributes | Suggestion | Detect numeric-only fields |
| MEILI-S004 | Empty filterableAttributes | Info | No filterable attrs configured |
| MEILI-S005 | Unused filterableAttributes | Warning | Configured but never queried |
| MEILI-S006 | Missing stop words | Suggestion | Language detected, no stops |
| MEILI-S007 | Default ranking rules | Info | Using default order |
| MEILI-S008 | No distinct attribute | Suggestion | Potentially duplicate results |
| MEILI-S009 | Low pagination limit | Warning | maxTotalHits < 100 |
| MEILI-S010 | High pagination limit | Suggestion | maxTotalHits > 10000 |

### 5.2 Document Findings

| ID | Title | Severity | Detection |
|----|-------|----------|-----------|
| MEILI-D001 | Large documents | Warning | Avg size > 10KB or max > 100KB |
| MEILI-D002 | Inconsistent schema | Warning | Field presence varies > 20% |
| MEILI-D003 | Deep nesting | Warning | Object depth > 3 levels |
| MEILI-D004 | Large arrays | Warning | Array fields avg > 50 items |
| MEILI-D005 | HTML in text fields | Suggestion | HTML tags detected |
| MEILI-D006 | Empty field values | Info | >30% null/empty for a field |
| MEILI-D007 | Mixed types in field | Warning | Same field has string/number |
| MEILI-D008 | Very long text | Suggestion | Text > 65535 positions |

### 5.3 Performance Findings

| ID | Title | Severity | Detection |
|----|-------|----------|-----------|
| MEILI-P001 | High task failure rate | Critical | >10% failed tasks |
| MEILI-P002 | Slow indexing | Warning | Avg task duration > 5min |
| MEILI-P003 | Database fragmentation | Suggestion | used_db < 60% of db_size |
| MEILI-P004 | Too many indexes | Suggestion | >20 indexes |
| MEILI-P005 | Imbalanced indexes | Info | One index >80% of documents |
| MEILI-P006 | Too many fields | Warning | >100 unique fields per index |

### 5.4 Best Practices Findings

| ID | Title | Severity | Detection |
|----|-------|----------|-----------|
| MEILI-B001 | Settings after documents | Warning | Task order in history |
| MEILI-B002 | Duplicate searchable/filterable | Suggestion | Same fields in both |
| MEILI-B003 | Missing embedders config | Info | No AI/vector setup |
| MEILI-B004 | Old MeiliSearch version | Suggestion/Warning | Version < current stable |

---

## 6. Implementation Priorities

### Phase 1: Core Analysis (MVP) - ✅ COMPLETE
1. CLI with basic analyze command
2. Live instance collector
3. Schema analyzer (S001-S010)
4. JSON export
5. Basic console output

### Phase 2: Dump Support & Documents - ✅ COMPLETE
1. Dump file parser
2. Document analyzer (D001-D008)
3. Performance analyzer (P001-P006)
4. Markdown export

### Phase 3: Web Dashboard - ✅ COMPLETE
1. FastAPI application
2. Dashboard overview
3. Index detail views
4. Findings explorer
5. File upload for dumps

### Phase 4: Advanced Features - ✅ COMPLETE
1. ✅ SARIF export
2. ✅ Agent-friendly export
3. ✅ Fix script generation
4. ❌ Historical analysis (comparing dumps) - Not implemented
5. ✅ CI/CD integration mode

### Best Practices Analyzer - ✅ COMPLETE
1. ✅ B001: Settings after documents detection
2. ✅ B002: Duplicate searchable/filterable detection
3. ✅ B003: Missing embedders suggestions
4. ✅ B004: Old version detection

### Future Work
- Historical analysis (comparing dumps over time)
- Static assets directory (CSS/HTMX separate files)
- Document sampling endpoint for web dashboard

---

## 7. Usage Examples

### Example 1: Quick Health Check

```bash
$ uvx meilisearch-analyzer summary --url http://localhost:7700

╭─────────────────────────────────────────────────────────────────╮
│                    MeiliSearch Health Summary                   │
├─────────────────────────────────────────────────────────────────┤
│  Version: 1.12.0        Database: 4.0 GB        Indexes: 5      │
│                                                                 │
│  Health Score: 72/100  ████████████░░░░░░░░                     │
│                                                                 │
│  🔴 Critical: 2    🟡 Warnings: 8    🔵 Suggestions: 15         │
│                                                                 │
│  Top Issues:                                                    │
│  • products: Wildcard searchableAttributes                      │
│  • orders: Large documents (avg 45KB)                           │
│                                                                 │
│  Run 'analyze' for full report                                  │
╰─────────────────────────────────────────────────────────────────╯
```

### Example 2: Full Analysis with Export

```bash
$ uvx meilisearch-analyzer analyze \
    --url http://localhost:7700 \
    --api-key "your-key" \
    --output analysis.json \
    --format json

Connecting to MeiliSearch at http://localhost:7700...
Collecting data from 5 indexes...
  ✓ products (500,000 documents)
  ✓ orders (250,000 documents)
  ✓ customers (100,000 documents)
  ✓ categories (500 documents)
  ✓ reviews (400,000 documents)

Running analysis...
  ✓ Schema analysis: 10 findings
  ✓ Document analysis: 8 findings
  ✓ Performance analysis: 3 findings
  ✓ Best practices: 4 findings

Report saved to: analysis.json
```

### Example 3: Web Dashboard

```bash
$ uvx meilisearch-analyzer serve \
    --url http://localhost:7700 \
    --port 8080

Starting MeiliSearch Analyzer Dashboard...
Dashboard available at: http://localhost:8080

Press Ctrl+C to stop
```

---

## 8. Appendix: API Reference

### MeiliSearch API Endpoints Used

```
GET  /                           # Root info
GET  /health                     # Health check
GET  /version                    # Version info
GET  /stats                      # Global stats
GET  /indexes                    # List all indexes
GET  /indexes/{uid}              # Index info
GET  /indexes/{uid}/settings     # Index settings
GET  /indexes/{uid}/stats        # Index stats
GET  /indexes/{uid}/documents    # Sample documents
GET  /tasks                      # Task history
GET  /metrics                    # Prometheus metrics (if enabled)
```

### Settings Object Reference

```json
{
  "displayedAttributes": ["*"],
  "searchableAttributes": ["*"],
  "filterableAttributes": [],
  "sortableAttributes": [],
  "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
  "stopWords": [],
  "synonyms": {},
  "distinctAttribute": null,
  "typoTolerance": {
    "enabled": true,
    "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9},
    "disableOnWords": [],
    "disableOnAttributes": []
  },
  "faceting": {"maxValuesPerFacet": 100},
  "pagination": {"maxTotalHits": 1000},
  "proximityPrecision": "byWord"
}
```

---

*Document Version: 1.2.0*
*Last Updated: 2026-01-01*
*Implementation Status: All Phases Complete (28 finding types implemented)*
