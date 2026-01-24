# Rebuilding Meiliscan: production MVP architecture and implementation plan

A decoupled Go backend with OpenTUI-compatible TUI and HTMX web interface offers the optimal path for building a production-ready Meilisearch debugging tool that can analyze terabyte-scale indexes without excessive memory consumption. The architecture separates concerns into three layers—a streaming data analyzer, an OpenAPI-first REST backend, and pluggable frontends—enabling both terminal and web users to troubleshoot Meilisearch instances and dump files efficiently.

## Existing landscape and redesign rationale

The meiliscan proof-of-concept repository (github.com/asabla/meiliscan) was inaccessible during research, suggesting it may be private or in early development. Based on typical Python TUI tools for Meilisearch, we can infer a monolithic architecture coupling UI directly to data access—a pattern unsuitable for production workloads.

**Key redesign drivers** include memory efficiency for terabyte indexes (the PoC likely loads data into memory), the need for both TUI and web interfaces sharing a single API, and support for offline dump analysis alongside live instance debugging. The new architecture introduces a clean separation: a Go backend handles all data processing with streaming primitives, while frontends consume a spec-first OpenAPI over HTTP or Server-Sent Events.

OpenTUI, the target TUI framework from anomaly.co, is a **pure rendering library** with no built-in backend communication. It provides TypeScript/Zig-based terminal rendering with React, SolidJS, and Vue reconcilers, plus Go bindings. Applications must implement their own HTTP/SSE clients—meaning the meiliscan TUI will need to connect to the Go backend via standard REST/SSE protocols.

## Meilisearch data structures and analysis requirements

Understanding Meilisearch internals is critical for building an effective debugging tool. **Dump files** are gzip-compressed tar archives containing:

- `metadata.json` with instance info and dump version (V6+ for Meilisearch 1.x)
- `indexes/{uid}/documents.jsonl` storing documents as newline-delimited JSON
- `indexes/{uid}/settings.json` with index configuration
- `tasks/queue.jsonl` containing task history
- `keys/keys.json` for API key export

Documents are stored as single large JSONL files that can span multiple gigabytes. **No streaming decompression** exists in older Meilisearch versions, making efficient parsing essential for the debugging tool.

For live instances, the HTTP API provides comprehensive diagnostic endpoints: `/stats` for database and index metrics, `/tasks` with keyset pagination for queue inspection, `/indexes/{uid}/settings` for configuration analysis, and the experimental `/metrics` endpoint for Prometheus-format telemetry when enabled. The `/health` endpoint remains unauthenticated for monitoring integration.

**Common debugging scenarios** the tool must address include: diagnosing slow indexing (checking `isIndexing` status and task durations), identifying task queue backlogs (filtering by status/type), troubleshooting search relevancy (analyzing ranking rules and searchable attribute order), and monitoring memory/disk usage (comparing `databaseSize` vs `usedDatabaseSize` in LMDB).

At terabyte scale, Meilisearch uses LMDB with memory-mapped files. The database can reach 2 TiB maximum, and LMDB doesn't reclaim disk space on document deletion—critical context for users analyzing large indexes.

## Go as the optimal backend language

After evaluating Go and C# for this specific use case, **Go emerges as the clear choice** for several compelling reasons:

| Factor | Go Advantage |
|--------|-------------|
| **Memory control** | `syscall.Mmap` bypasses GC entirely; goroutine stacks start at 2 KB |
| **Binary distribution** | Single static binary, trivial cross-compilation via `GOOS/GOARCH` |
| **OpenAPI tooling** | oapi-codegen provides mature spec-first code generation |
| **Startup time** | <50ms typical, critical for CLI tools |
| **Streaming JSON** | `encoding/json.Decoder` with `Token()`/`More()` for incremental parsing |

Go's GC is optimized for low latency with stop-the-world pauses under **100 microseconds**. The `GOMEMLIMIT` environment variable enables hard memory caps, essential for ensuring the debugging tool doesn't consume more RAM than Meilisearch itself. Libraries like `fxamacker/cbor` (used by Kubernetes and Let's Encrypt) provide production-grade CBOR streaming for dump parsing.

C# with Native AOT has improved significantly—binary sizes dropped **50%** from .NET 7 to .NET 8—but cross-compilation remains unsupported, requiring builds on each target platform. The OpenAPI ecosystem is also in flux: Swashbuckle is being removed from .NET 9 templates due to maintenance issues, while Go's oapi-codegen remains actively developed and stable.

For memory-mapped file access to large indexes, Go packages like `edsrzf/mmap-go` deliver **25x faster random access** than `ReaderAt` when data is in page cache. Combined with `sync.Pool` for object reuse, Go enables processing millions of documents without proportional memory growth.

## System architecture: decoupled frontend/backend design

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI Entry Point                             │
│  meiliscan [flags]        → TUI mode (default)                      │
│  meiliscan serve [flags]  → HTTP server for web UI                  │
│  meiliscan analyze <dump> → One-shot dump analysis                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────┐       ┌───────────────────────────────┐
│      TUI Frontend         │       │       Web Frontend            │
│  • OpenTUI Go bindings    │       │  • HTMX + templ templates     │
│  • Direct SDK calls for   │       │  • SSE for live updates       │
│    fast local access      │       │  • Virtual scroll for large   │
│  • Optional HTTP for      │       │    result sets                │
│    remote instances       │       │                               │
└───────────────────────────┘       └───────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Go Backend Server                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   OpenAPI HTTP Layer                         │   │
│  │  • oapi-codegen generated handlers (Chi router)             │   │
│  │  • Request validation middleware                            │   │
│  │  • SSE endpoint for streaming results                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                │                                     │
│  ┌─────────────────────────────▼───────────────────────────────┐   │
│  │                   Analysis Core                              │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │   │
│  │  │ Dump Analyzer  │  │ Live Instance  │  │   Results    │  │   │
│  │  │ • GZIP stream  │  │ • HTTP client  │  │   Cache      │  │   │
│  │  │ • NDJSON parse │  │ • Rate limiting│  │   (optional) │  │   │
│  │  │ • Mmap for idx │  │ • Pagination   │  │              │  │   │
│  │  └────────────────┘  └────────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

The **TUI frontend** can operate in two modes: direct SDK calls when analyzing local dump files (for maximum performance), or HTTP communication when the backend runs as a separate process. This flexibility supports both fast local analysis and remote debugging scenarios.

The **web frontend** uses HTMX for server-driven interactivity, eliminating the need for a JavaScript build pipeline. The `templ` library provides type-safe Go HTML templates that compile to efficient code. SSE streams deliver real-time updates for long-running analysis operations.

## OpenAPI specification design

The API follows spec-first development with oapi-codegen generating server interfaces:

```yaml
openapi: 3.1.0
info:
  title: Meiliscan API
  version: 1.0.0
paths:
  /sources:
    get:
      summary: List configured data sources
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SourceList'
    post:
      summary: Add a data source (dump file or live instance)
      
  /sources/{sourceId}/indexes:
    get:
      summary: List indexes in source with stats
      
  /sources/{sourceId}/indexes/{indexId}/documents:
    get:
      summary: Stream documents with cursor pagination
      parameters:
        - name: cursor
          in: query
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            
  /sources/{sourceId}/tasks:
    get:
      summary: List tasks with filtering
      parameters:
        - name: status
          in: query
          schema:
            type: array
            items:
              enum: [enqueued, processing, succeeded, failed, canceled]
              
  /events:
    get:
      summary: SSE stream for analysis progress
      responses:
        '200':
          content:
            text/event-stream: {}
```

**Cursor-based pagination** is essential for virtual scrolling and large result sets—the API returns `nextCursor` and `hasMore` rather than offset-based pagination, which becomes slow on large datasets and inconsistent with concurrent writes.

## Implementation phases

### Phase 1: Core infrastructure (weeks 1-3)

Establish the project foundation with Go module structure, CLI framework, and OpenAPI tooling:

```
meiliscan/
├── cmd/
│   ├── root.go           # Cobra CLI root
│   ├── serve.go          # HTTP server command
│   └── analyze.go        # One-shot analysis command
├── api/
│   ├── openapi.yaml      # API specification
│   ├── generated.go      # oapi-codegen output
│   └── handlers.go       # Implementation
├── internal/
│   ├── analyzer/
│   │   ├── dump.go       # Dump file parsing
│   │   ├── live.go       # Live instance client
│   │   └── stream.go     # Streaming utilities
│   ├── index/
│   │   └── mmap.go       # Memory-mapped access
│   └── source/
│       └── registry.go   # Data source management
├── web/
│   ├── templates/        # templ components
│   └── static/           # HTMX, CSS
└── tui/
    └── app.go            # OpenTUI integration
```

**Key deliverables**: Working CLI skeleton, OpenAPI spec with generated types, basic HTTP server with health endpoint, and CI/CD pipeline producing cross-platform binaries.

### Phase 2: Dump analysis engine (weeks 4-6)

Build the streaming dump parser that never loads entire indexes into memory:

```go
func (a *DumpAnalyzer) StreamDocuments(ctx context.Context, indexUID string) (<-chan Document, error) {
    docs := make(chan Document, 100) // Bounded buffer
    
    go func() {
        defer close(docs)
        
        file, _ := a.openIndexDocuments(indexUID) // Opens JSONL within tar
        decoder := json.NewDecoder(file)
        
        for decoder.More() {
            select {
            case <-ctx.Done():
                return
            default:
                var doc Document
                if err := decoder.Decode(&doc); err != nil {
                    continue
                }
                docs <- doc
            }
        }
    }()
    
    return docs, nil
}
```

This phase implements gzip stream decompression, tar archive navigation without full extraction, and NDJSON line-by-line parsing. Memory usage remains constant regardless of dump size—only the bounded channel buffer consumes RAM.

### Phase 3: Live instance integration (weeks 7-8)

Create a Meilisearch HTTP client with intelligent pagination and rate limiting:

```go
type LiveClient struct {
    baseURL    string
    apiKey     string
    httpClient *http.Client
}

func (c *LiveClient) GetTasksStream(ctx context.Context, filters TaskFilters) (<-chan Task, error) {
    tasks := make(chan Task, 50)
    
    go func() {
        defer close(tasks)
        var cursor *int
        
        for {
            resp, err := c.fetchTasks(ctx, filters, cursor)
            if err != nil {
                return
            }
            
            for _, task := range resp.Results {
                tasks <- task
            }
            
            if resp.Next == nil {
                return // No more pages
            }
            cursor = resp.Next
        }
    }()
    
    return tasks, nil
}
```

The client automatically handles Meilisearch's keyset pagination (using `from` and `next` parameters) and exposes tasks, indexes, stats, and settings through a unified interface that works identically whether analyzing dumps or live instances.

### Phase 4: Web interface with HTMX (weeks 9-11)

Build the server-rendered web UI using templ components and HTMX attributes:

```go
// templates/index_list.templ
templ IndexList(indexes []Index) {
    <div id="indexes" hx-get="/indexes" hx-trigger="every 30s">
        for _, idx := range indexes {
            @IndexCard(idx)
        }
    </div>
}

templ IndexCard(idx Index) {
    <div class="card" hx-get={ fmt.Sprintf("/indexes/%s/details", idx.UID) }
         hx-target="#detail-panel" hx-swap="innerHTML">
        <h3>{ idx.UID }</h3>
        <span class="stat">{ fmt.Sprintf("%d docs", idx.DocumentCount) }</span>
        if idx.IsIndexing {
            <span class="badge indexing">Indexing...</span>
        }
    </div>
}
```

SSE integration delivers real-time progress for long-running analysis:

```go
func (h *Handler) EventsStream(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "text/event-stream")
    w.Header().Set("Cache-Control", "no-cache")
    
    flusher := w.(http.Flusher)
    
    for {
        select {
        case <-r.Context().Done():
            return
        case event := <-h.eventBus:
            fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event.Type, event.JSON())
            flusher.Flush()
        }
    }
}
```

### Phase 5: TUI with OpenTUI (weeks 12-14)

Integrate OpenTUI's Go bindings for terminal rendering. Since OpenTUI provides no backend communication, the TUI will embed HTTP client logic:

```go
package tui

import (
    "github.com/anomalyco/opentui/packages/go"
)

func (app *App) Run() error {
    renderer := opentui.NewRenderer(app.width, app.height)
    defer renderer.Close()
    
    // Start analysis in background
    go app.startAnalysis()
    
    for {
        buffer, _ := renderer.GetNextBuffer()
        app.render(buffer)
        renderer.Render(true)
        
        // Handle keyboard input
        key := renderer.PollInput()
        if key.Name == "q" {
            return nil
        }
        app.handleKey(key)
    }
}
```

For local dump analysis, the TUI calls the analyzer directly without HTTP overhead. For remote debugging, it connects to a running `meiliscan serve` instance via the same OpenAPI client used by the web frontend.

## Large-scale data handling strategies

Processing terabyte indexes requires careful memory management. **Three key strategies** ensure the tool remains efficient:

**Memory-mapped file access** for index inspection:
```go
func (a *Analyzer) MmapIndexFile(path string) ([]byte, error) {
    f, _ := os.Open(path)
    defer f.Close()
    
    stat, _ := f.Stat()
    data, err := syscall.Mmap(int(f.Fd()), 0, int(stat.Size()),
        syscall.PROT_READ, syscall.MAP_SHARED)
    // OS manages paging; only accessed regions consume RAM
    return data, err
}
```

**Streaming aggregations** for statistics:
```go
type StreamingStats struct {
    count      int64
    sizeSum    int64
    fieldCounts map[string]int64
}

func (s *StreamingStats) Process(doc Document) {
    s.count++
    s.sizeSum += int64(len(doc.Raw))
    for field := range doc.Fields {
        s.fieldCounts[field]++
    }
}
```

**Bounded concurrency** for parallel processing:
```go
sem := make(chan struct{}, runtime.NumCPU())
for doc := range documents {
    sem <- struct{}{}
    go func(d Document) {
        defer func() { <-sem }()
        analyze(d)
    }(doc)
}
```

## Technology recommendations summary

| Component | Recommendation | Justification |
|-----------|---------------|---------------|
| **Language** | Go 1.22+ | Memory efficiency, single binary, excellent streaming |
| **CLI Framework** | Cobra | Industry standard (kubectl, docker, terraform) |
| **HTTP Router** | Chi | Lightweight, oapi-codegen native support |
| **OpenAPI Generator** | oapi-codegen | Mature spec-first, generates interfaces |
| **HTML Templates** | templ | Type-safe, compiles to Go, HTMX-friendly |
| **TUI Framework** | OpenTUI Go bindings | High performance Zig core, familiar API |
| **JSON Streaming** | encoding/json + simdjson-go | Standard for compatibility, SIMD for hot paths |
| **CBOR Parsing** | fxamacker/cbor | Production-grade, RFC 8949 compliant |

The architecture prioritizes **separation of concerns** (data analysis vs presentation), **memory efficiency** (streaming everywhere, mmap for large files), and **deployment simplicity** (single binary with embedded assets). By building on OpenAPI spec-first principles, both the TUI and web frontends share identical API semantics, reducing maintenance burden and ensuring feature parity across interfaces.
