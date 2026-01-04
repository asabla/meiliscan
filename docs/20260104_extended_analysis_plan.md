# Extended analysis plan (production self-hosted)

Date: 2026-01-04

This document outlines the next set of analytics to add to **meiliscan**, focusing on **self-hosted production** Meilisearch instances.

Goals:
- Expand actionable findings for performance tuning, reliability, and best practices.
- Prefer **high-signal** checks with low false-positive rates.
- Add **optional enhancements** (e.g., config file ingestion, search probes) that are **silent when not enabled/provided**.

Non-goals:
- Do not require access to the host machine.
- Do not assume a `config.toml` always exists.
- Do not introduce destructive operations against an instance.

---

## Implementation Status

| Workstream | Status | Notes |
|------------|--------|-------|
| 1) Instance launch config analytics | **DONE** | CLI flag, model, analyzer, findings I001-I006 |
| 2) Opt-in search probing | **DONE** | CLI flag, analyzer, findings Q001-Q003 |
| 3) Expand index setting analytics | **DONE** | S011-S020 implemented in schema_analyzer.py |
| 4) Expand document/sample analytics | **PARTIAL** | D009-D010 (PII) done; D011 pending |
| 5) Task-based performance analytics | **DONE** | P007-P010 implemented in performance_analyzer.py |

---

## Current coverage (baseline)

Today meiliscan evaluates:
- Index-level settings: searchable/filterable/displayed attributes, stop words, ranking rules, distinct attribute, pagination.
- Document samples: size, depth, arrays, markup, empty fields, mixed types, long text.
- Instance behavior from tasks: failure rate, slow indexing, settings after documents.
- Global stats heuristics: database fragmentation, index count/imbalance.
- Version freshness.

This plan adds **instance launch config**, **more index/document checks**, and **opt-in probing**.

---

## Workstreams

### 1) Optional instance launch config analytics (via `config.toml`) - **IMPLEMENTED**

**User constraints**
- `config.toml` is **optional** input.
- If no file is provided, these checks are **skipped silently** (no "unknown" findings).

**Proposed CLI extension** - **DONE**
- Add optional argument to `meiliscan analyze`:
  - `--config-toml PATH`
- This keeps the UX simple while enabling enhanced audits.

**Proposed internal model** - **DONE**
- Add `InstanceLaunchConfig` model that stores normalized values parsed from TOML.
- Store it on the report source metadata and expose to analyzers via `analyze_global`.

**Implementation files:**
- `meiliscan/models/instance_config.py` - `InstanceLaunchConfig` Pydantic model
- `meiliscan/analyzers/instance_config_analyzer.py` - `InstanceConfigAnalyzer`
- `meiliscan/cli.py` - `--config-toml` flag wiring

**TOML keys to support initially (from docs)** - **DONE**
- Security & environment
  - `env` (production/development)
  - `master_key` (presence/timing/strength checks where possible)
  - `http_addr`
  - `ssl_*` keys (presence)
- Operations
  - `log_level`, `experimental_logs_mode`
- Performance tuning
  - `max_indexing_memory`, `max_indexing_threads`
  - `http_payload_size_limit`
  - `experimental_search_queue_size`
  - `experimental_embedding_cache_entries`
  - batched tasks limits (`experimental_max_number_of_batched_tasks`, `experimental_limit_batched_tasks_total_size`)
- Reliability
  - snapshots (`schedule_snapshot`, `snapshot_dir`, `experimental_no_snapshot_compaction`)
  - dumps (`dump_dir`, `import_dump`, ignore flags)
  - snapshot import flags and ignore flags

**Instance-level findings (only when `--config-toml` provided)** - **DONE**
- `MEILI-I001` (Critical): `env=production` but `master_key` missing/too short.
- `MEILI-I002` (Warning): `http_addr` binds to `0.0.0.0:*` without SSL settings configured.
- `MEILI-I003` (Suggestion): `log_level` set to `DEBUG`/`TRACE` in production.
- `MEILI-I004` (Info/Suggestion): snapshots not scheduled in production.
- `MEILI-I005` (Warning): `http_payload_size_limit` extreme values (too low / too high).
- `MEILI-I006` (Suggestion): indexing memory/threads values likely risky (e.g., threads == all cores, memory >= total RAM) — note: may require user-supplied host capacity to be precise.

Notes:
- Some checks require machine sizing to be fully accurate; if not available, prefer conservative messaging.
- Avoid generating findings that require privileged OS introspection.

---

### 2) Opt-in search probing (read-only) - **IMPLEMENTED**

**User constraints**
- Probing should be opt-in.
- Default behavior stays "passive" (settings/stats/tasks/samples only).

**Proposed CLI extension** - **DONE**
- Add optional flag:
  - `--probe-search`

**Implementation files:**
- `meiliscan/analyzers/search_probe_analyzer.py` - `SearchProbeAnalyzer`
- `meiliscan/cli.py` - `--probe-search` flag wiring

**Probe types** - **DONE**
- Sort smoke test:
  - For each index with `sortableAttributes`, pick 1–2 configured fields and attempt a simple search with `sort=["field:asc"]`.
- Filter smoke test:
  - For each index with `filterableAttributes`, select a candidate field/value from sample docs and attempt a filter query.

**Probe findings** - **DONE**
- `MEILI-Q001` (Warning): configured sort fails (invalid attribute/type).
- `MEILI-Q002` (Warning): configured filter fails.
- `MEILI-Q003` (Info): response payload unusually large for default query (heuristic, helps validate `displayedAttributes`).

Implementation notes:
- Keep total probes bounded (e.g., max 3 probes per index).
- Never use user-provided queries; probes should be generated only from collected settings + sample docs.

---

### 3) Expand index setting analytics - **DONE**

The `IndexSettings` model already contains more than we currently analyze.

**Implementation file:** `meiliscan/analyzers/schema_analyzer.py`

**Primary key** - **DONE**
- `MEILI-S011` (Critical): index has no `primaryKey` (or sample docs missing the primary key field).
- `MEILI-S012` (Warning): primary key looks mutable/non-identifier (heuristic: matches common non-id field names like `title`, `name`).

**Sortable attributes** - **DONE**
- `MEILI-S013` (Info): no sortable attributes configured (only if index seems to contain common sort candidates like `createdAt`, `price`, `rating`).
- `MEILI-S014` (Warning): sortable attribute has inconsistent types across sample docs or contains complex types (arrays/objects).

**Filterable attributes** - **DONE**
- `MEILI-S015` (Suggestion): filterable attribute appears high-cardinality (email/uuid/token patterns or sample analysis) — potential faceting/filter performance risk.

**Faceting** - **DONE**
- `MEILI-S016` (Info/Suggestion): `faceting.maxValuesPerFacet` is low/high relative to observed values (heuristic from samples).

**Synonyms** - **DONE**
- `MEILI-S017` (Suggestion): synonyms set is unusually large or contains suspicious entries (empty, self-synonyms, very long chains, etc.).

**Typo tolerance** - **DONE**
- `MEILI-S018` (Suggestion): typo tolerance enabled on identifier-heavy indexes; suggest using `disableOnAttributes` for ID-like fields.
- `MEILI-S019` (Info): extremely permissive `minWordSizeForTypos` settings.

**Tokenization / dictionary** - **DONE**
- `MEILI-S020` (Info/Suggestion): unusually large `dictionary` list (maintenance risk); duplicate entries; separator token configs appear suspicious (alphanumeric or very long).

---

### 4) Expand document/sample analytics - **PARTIAL**

Use sample documents as heuristics; default remains `limit=20`.

**Sampling control** - **DONE**
- Add optional argument:
  - `--sample-documents N` (default `20`)

**Additional checks**
- `MEILI-D009` (Warning): ~~arrays of objects detected~~ **CHANGED**: Potentially sensitive field names detected. **DONE**
- `MEILI-D010` (Critical): ~~candidate filter/facet fields detected~~ **CHANGED**: Potential PII detected in document content (opt-in via `--detect-sensitive`). **DONE**
- `MEILI-D011` (Opt-in / Warning): potential PII fields detected (email/phone/token/password patterns). **PENDING** - merged into D009/D010.

**Implementation files:**
- `meiliscan/analyzers/document_analyzer.py` - PII detection methods added
- `meiliscan/cli.py` - `--sample-documents` and `--detect-sensitive` flags

Notes:
- PII detection should be conservative and based on field names + value patterns.

---

### 5) Expand task-based performance analytics - **DONE**

**Implementation file:** `meiliscan/analyzers/performance_analyzer.py`

**Backlog detection** - **DONE**
- `MEILI-P007` (Warning): sustained task backlog (enqueuedAt vs startedAt suggests queueing delays >60s average).

**Indexing pattern recommendations** - **DONE**
- `MEILI-P008` (Suggestion): too many tiny indexing tasks (<10 docs, >50% of tasks) — suggest client-side batching.
- `MEILI-P009` (Suggestion): oversized indexing tasks (>10 minute duration) — suggest smaller batches/doc reduction.

**Error clustering** - **DONE**
- `MEILI-P010` (Warning): top recurring failure reasons from task error payloads (error codes appearing ≥3 times).

---

## Data model & plumbing changes - **DONE**

- Extend the analysis pipeline to optionally include:
  - `InstanceLaunchConfig` (parsed from TOML) - **DONE** (`meiliscan/models/instance_config.py`)
  - `probe_results` (if `--probe-search`) stored in report metadata - **DONE** (via `_probe_findings` in `analysis_options`)
  - configurable `sample_documents` count - **DONE** (`LiveInstanceCollector.sample_docs`)
- Ensure exporters (JSON/Markdown/Web/SARIF) gracefully handle additional metadata. - **DONE** (findings flow through existing pipeline)

---

## Testing plan - **DONE**

- Add unit tests for TOML parsing and instance-config findings. - **DONE** (44 tests in `test_instance_config_analyzer.py`)
- Add analyzer tests for new Schema/Document/Performance findings. - **DONE**
  - 27 new tests for S011-S020 in `test_schema_analyzer.py` (41 total)
  - 18 new tests for P007-P010 in `test_performance_analyzer.py` (41 total)
  - 23 tests for Q001-Q003 in `test_search_probe_analyzer.py`
- Add mock live-collector tests for `--probe-search` behavior (mock `search()` results). - **DONE** (covered in search probe tests)

**Total test count: 376 tests passing**

---

## Rollout plan - **MOSTLY COMPLETE**

1. Implement CLI + data plumbing for optional inputs (config toml, sample-documents, probe-search). - **DONE**
2. Add instance-config analyzer and 2–3 high-value findings first (`I001`, `I004`, `I003`). - **DONE** (all I001-I006)
3. Add index/document improvements (primary key, sortable types, arrays-of-objects). - **DONE** (S011-S020)
4. Add task backlog + error clustering. - **DONE** (P007-P010)
5. Iterate on thresholds based on real-world feedback. - **PENDING**

---

## Remaining work

1. **Document analytics expansion (D011)**: Consider additional document-level checks beyond PII detection.
2. **Real-world validation**: Test findings against production instances to tune thresholds.
3. **Documentation**: Update README with new CLI flags and finding descriptions.
