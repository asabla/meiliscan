# Meiliscan Go Refactor: Implementation Plan

This document outlines the implementation plan for refactoring Meiliscan from Python to Go, based on the architecture defined in `research_notes.md`.

## Decision Summary

| Decision | Choice |
|----------|--------|
| **Primary driver** | Better architecture (clean separation of concerns) |
| **Scope** | MVP first, iterate |
| **Transition** | Clean break (archive Python code) |
| **TUI framework** | OpenTUI (required) |
| **Priority findings** | Schema (S*), Performance (P*), Critical severity |
| **Timeline** | Ongoing/hobby pace |
| **Repository** | Same repo (archive Python to subdirectory) |
| **Interface priority** | CLI and Web equal |

---

## Current Python Codebase (Reference)

**What exists today:**
- **42 finding types** across 6 categories:
  - Schema: S001-S020
  - Documents: D001-D013
  - Performance: P001-P010
  - Best Practices: B001-B004
  - Instance Config: I001-I006
  - Search Probes: Q001-Q003
- **CLI commands**: `analyze`, `summary`, `tasks`, `fix-script`, `compare`, `serve`
- **Web dashboard**: FastAPI + Jinja2 templates
- **4 exporters**: JSON, Markdown, SARIF, Agent-friendly
- **2 collectors**: LiveInstanceCollector (HTTP), DumpParser (tar.gz)
- **16 test files** covering all analyzers, exporters, and collectors
- **Seed data generator**: 17+ index generators with size presets

---

## MVP Feature Definition

### MVP Must-Haves

| Feature | Current Python | MVP Go |
|---------|---------------|--------|
| **CLI** | Typer + Rich | Cobra |
| **Data Sources** | Live instance + Dump files | Both |
| **Findings** | 42 total | ~15 (prioritized) |
| **Export formats** | JSON, Markdown, SARIF, Agent | JSON + Markdown |
| **Web UI** | FastAPI + Jinja2 | HTMX + templ |
| **TUI** | None | OpenTUI |

### MVP Findings (Priority Order)

Based on criteria: Schema, Performance, Critical severity, commonly encountered.

| ID | Title | Severity | Category |
|----|-------|----------|----------|
| **S001** | Wildcard searchableAttributes | Critical | Schema |
| **S011** | Missing primary key | Critical | Schema |
| **P001** | High task failure rate | Critical | Performance |
| **D010** | PII content detected | Critical | Documents |
| **I001** | Production without master key | Critical | Instance |
| **S002** | ID fields in searchableAttributes | Warning | Schema |
| **S009** | Very low pagination limit | Warning | Schema |
| **P002** | Slow indexing | Warning | Performance |
| **P007** | Task queue backlog | Warning | Performance |
| **S003** | Numeric fields in searchableAttributes | Suggestion | Schema |
| **S004** | Empty filterableAttributes | Info | Schema |
| **S006** | No stop words configured | Suggestion | Schema |
| **S007** | Default ranking rules | Info | Schema |
| **P003** | Database fragmentation | Suggestion | Performance |
| **P004** | Too many indexes | Suggestion | Performance |

This gives us **15 high-value findings** for MVP.

---

## Project Structure (Go)

```
meiliscan/
├── archive/                    # Archived Python v1 code
│   └── python-v1/
├── cmd/
│   └── meiliscan/
│       └── main.go             # Entry point
├── internal/
│   ├── analyzer/
│   │   ├── analyzer.go         # Analyzer interface
│   │   ├── schema.go           # Schema findings (S001-S011, etc.)
│   │   ├── performance.go      # Performance findings (P001-P007)
│   │   └── registry.go         # Analyzer registration
│   ├── collector/
│   │   ├── collector.go        # Collector interface
│   │   ├── live.go             # Live Meilisearch HTTP client
│   │   └── dump.go             # Dump file streaming parser
│   ├── finding/
│   │   ├── finding.go          # Finding model + severity/category enums
│   │   └── registry.go         # Finding metadata registry
│   ├── exporter/
│   │   ├── exporter.go         # Exporter interface
│   │   ├── json.go             # JSON output
│   │   └── markdown.go         # Markdown output
│   ├── report/
│   │   └── report.go           # Report model + health scoring
│   └── cli/
│       ├── root.go             # Root command + global flags
│       ├── analyze.go          # analyze command
│       ├── serve.go            # serve command
│       └── summary.go          # summary command
├── api/
│   ├── openapi.yaml            # OpenAPI 3.1 spec
│   ├── generated.go            # oapi-codegen output
│   └── handlers.go             # HTTP handlers
├── web/
│   ├── templates/              # templ components
│   │   ├── layout.templ
│   │   ├── dashboard.templ
│   │   ├── findings.templ
│   │   └── index_detail.templ
│   └── static/
│       ├── htmx.min.js
│       └── styles.css
├── tui/
│   └── app.go                  # OpenTUI integration
├── pkg/
│   └── meilisearch/
│       └── client.go           # Reusable Meilisearch HTTP client
├── testdata/
│   └── dumps/                  # Test dump files
├── scripts/
│   └── seed/                   # Seed data generation
├── docs/
│   └── 20260118_refactor_mvp/  # Planning documents
├── go.mod
├── go.sum
├── Makefile
├── README.md
└── AGENTS.md
```

---

## Implementation Milestones

Since this is an ongoing/hobby project, we use a **vertical slice approach** where each milestone delivers working, usable functionality.

### Milestone 1: "Hello World" Analysis
**Goal**: `meiliscan analyze --url` outputs JSON report with 5 findings

**Deliverables**:
- Go module + Cobra CLI foundation
- Live instance collector (fetch settings/stats only)
- 5 core findings: S001, S002, S004, S007, P004
- JSON exporter
- Basic health score

**Exit criteria**: Working CLI that connects to Meilisearch and outputs JSON

---

### Milestone 2: Dump File Support
**Goal**: `meiliscan analyze --dump` works

**Deliverables**:
- Streaming dump parser (tar.gz + JSONL)
- Share analyzer interface between live/dump
- Test fixtures with sample dumps

**Exit criteria**: Analyze both live instances and dumps

---

### Milestone 3: Rich CLI Output
**Goal**: Beautiful terminal output matching Python version quality

**Deliverables**:
- Add 10 more findings (S003, S006, S009, S011, P001, P002, P003, P007, D010, I001)
- lipgloss/glamour for styled output
- Summary command
- Markdown exporter
- CI mode with exit codes

**Exit criteria**: CLI feature parity with Python for core use cases

---

### Milestone 4: Web Backend
**Goal**: OpenAPI backend serving analysis data

**Deliverables**:
- OpenAPI 3.1 spec
- oapi-codegen handlers
- Chi router + middleware
- `/api/analyze`, `/api/health`, `/api/report` endpoints
- SSE for streaming progress

**Exit criteria**: REST API that any frontend can consume

---

### Milestone 5: Web Frontend
**Goal**: Dashboard with core features

**Deliverables**:
- templ templates
- HTMX interactions
- Dashboard (health gauge, summary)
- Findings list with filters
- Index detail view

**Exit criteria**: Web dashboard matching core Python functionality

---

### Milestone 6: OpenTUI ✅
**Goal**: TUI for terminal users

**Status**: Complete

**Deliverables**:
- ~~OpenTUI Go bindings~~ → TypeScript/Bun implementation instead
- ✅ Analysis view (connects via API)
- ✅ Findings browser with filtering
- ✅ Finding detail view
- ⏳ Direct SDK mode for dumps (not implemented - post-MVP)

**What exists** (`tui/` directory):
- TypeScript app using `@opentui/core` (v0.1.74)
- Connects to Go API server (`POST /api/analyze`)
- Views: Welcome → Connecting → Dashboard → Findings → Finding Detail → Help
- Keyboard navigation (vim-style j/k, PageUp/PageDown, Home/End)
- Severity and category filtering
- Preview pane
- Terminal size adaptation (responsive layout)
- Help screen with keyboard shortcuts

**Keyboard shortcuts**:
- Global: `Ctrl+C` quit, `?` help, `Esc` back
- Navigation: `↑↓/jk`, `PgUp/Ctrl+U`, `PgDn/Ctrl+D`, `Home/g`, `End/G`
- Findings: `1-4` severity filter, `C` category filter, `A/0` clear filters, `Enter` details
- Dashboard: `F` findings, `R` refresh, `D` disconnect

**Known limitations**:
- Requires separate API server running (`meiliscan serve`)
- No direct dump analysis (must go through API)

**Exit criteria**: Terminal UI alternative to CLI - **COMPLETE**

---

### Post-MVP Milestones

- Document analyzer (D001-D013)
- Best practices analyzer (B001-B004)
- Instance config analyzer (I001-I006)
- SARIF + Agent exporters
- Historical comparison
- Search probes
- PII detection

---

## Key Dependencies (Go)

| Purpose | Package |
|---------|---------|
| CLI | `github.com/spf13/cobra` |
| HTTP client | `net/http` (stdlib) |
| JSON streaming | `encoding/json` (stdlib) |
| OpenAPI codegen | `github.com/oapi-codegen/oapi-codegen` |
| HTTP router | `github.com/go-chi/chi/v5` |
| HTML templates | `github.com/a-h/templ` |
| Terminal styling | `github.com/charmbracelet/lipgloss` |
| TUI | OpenTUI Go bindings |
| Testing | `testing` + `github.com/stretchr/testify` |
| Tar/Gzip | `archive/tar`, `compress/gzip` |

---

## Migration Strategy

1. **Archive Python code**: Move to `archive/python-v1/` directory
2. **Initialize Go module**: `go mod init github.com/asabla/meiliscan`
3. **Implement milestones**: Work through each milestone sequentially
4. **Reference Python**: Use archived code as reference for analyzer logic and finding definitions

The archived Python code remains available for:
- Reference during implementation
- Comparing analyzer logic
- Extracting test cases and expected outputs
- Documentation reference

---

## Success Criteria

### MVP Complete When:
- [x] `meiliscan analyze --url` produces JSON report with 15 findings ✅ (51 findings!)
- [x] `meiliscan analyze --dump` works with streaming parser ✅
- [x] `meiliscan serve` launches web dashboard with dashboard/findings/index views ✅
- [x] TUI mode available via OpenTUI ✅ (partial - needs polish)
- [x] CI mode with appropriate exit codes ✅
- [x] Cross-platform binaries via GoReleaser ✅

### Quality Gates:
- All analyzers have unit tests ✅
- Integration tests for collectors (live + dump) ✅
- Web UI has basic E2E tests ✅
- Documentation updated for Go version ✅
