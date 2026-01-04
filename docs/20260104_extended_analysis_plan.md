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

### 1) Optional instance launch config analytics (via `config.toml`)

**User constraints**
- `config.toml` is **optional** input.
- If no file is provided, these checks are **skipped silently** (no “unknown” findings).

**Proposed CLI extension**
- Add optional argument to `meiliscan analyze`:
  - `--config-toml PATH`
- This keeps the UX simple while enabling enhanced audits.

**Proposed internal model**
- Add `InstanceLaunchConfig` model that stores normalized values parsed from TOML.
- Store it on the report source metadata and expose to analyzers via `analyze_global`.

**TOML keys to support initially (from docs)**
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

**Instance-level findings (only when `--config-toml` provided)**
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

### 2) Opt-in search probing (read-only)

**User constraints**
- Probing should be opt-in.
- Default behavior stays “passive” (settings/stats/tasks/samples only).

**Proposed CLI extension**
- Add optional flag:
  - `--probe-search`

**Probe types**
- Sort smoke test:
  - For each index with `sortableAttributes`, pick 1–2 configured fields and attempt a simple search with `sort=["field:asc"]`.
- Filter smoke test:
  - For each index with `filterableAttributes`, select a candidate field/value from sample docs and attempt a filter query.

**Probe findings**
- `MEILI-Q001` (Warning): configured sort fails (invalid attribute/type).
- `MEILI-Q002` (Warning): configured filter fails.
- `MEILI-Q003` (Info): response payload unusually large for default query (heuristic, helps validate `displayedAttributes`).

Implementation notes:
- Keep total probes bounded (e.g., max 3 probes per index).
- Never use user-provided queries; probes should be generated only from collected settings + sample docs.

---

### 3) Expand index setting analytics

The `IndexSettings` model already contains more than we currently analyze.

**Primary key**
- `MEILI-S011` (Critical): index has no `primaryKey` (or sample docs missing the primary key field).
- `MEILI-S012` (Warning): primary key looks mutable/non-identifier (heuristic: matches common non-id field names like `title`, `name`).

**Sortable attributes**
- `MEILI-S013` (Info): no sortable attributes configured (only if index seems to contain common sort candidates like `createdAt`, `price`, `rating`).
- `MEILI-S014` (Warning): sortable attribute has inconsistent types across sample docs.

**Filterable attributes**
- `MEILI-S015` (Suggestion): filterable attribute appears high-cardinality (email/uuid/token patterns) — potential faceting/filter performance risk.

**Faceting**
- `MEILI-S016` (Info/Suggestion): `faceting.maxValuesPerFacet` is low/high relative to observed values (heuristic from samples).

**Synonyms**
- `MEILI-S017` (Suggestion): synonyms set is unusually large or contains suspicious entries (empty, self-synonyms, etc.).

**Typo tolerance**
- `MEILI-S018` (Suggestion): typo tolerance enabled on identifier-heavy indexes; suggest using `disableOnAttributes` for ID-like fields.
- `MEILI-S019` (Info): extremely permissive `minWordSizeForTypos` settings.

**Tokenization / dictionary**
- `MEILI-S020` (Info/Suggestion): unusually large `dictionary` list (maintenance risk); separator token configs appear suspicious.

---

### 4) Expand document/sample analytics

Use sample documents as heuristics; default remains `limit=20`.

**Sampling control**
- Add optional argument:
  - `--sample-documents N` (default `20`)

**Additional checks**
- `MEILI-D009` (Warning): arrays of objects detected (flattening can lead to confusing fields and filtering behavior).
- `MEILI-D010` (Suggestion): candidate filter/facet fields detected (low-cardinality fields) but not configured.
- `MEILI-D011` (Opt-in / Warning): potential PII fields detected (email/phone/token/password patterns). Default off; enable with `--detect-sensitive`.

Notes:
- PII detection should be conservative and based on field names + value patterns.

---

### 5) Expand task-based performance analytics

**Backlog detection**
- `MEILI-P007` (Warning): sustained task backlog (enqueuedAt vs finishedAt suggests queueing delays).

**Indexing pattern recommendations**
- `MEILI-P008` (Suggestion): too many tiny indexing tasks (suggest client-side batching).
- `MEILI-P009` (Suggestion): oversized indexing tasks (suggest smaller batches/doc reduction) based on durations and/or error messages.

**Error clustering**
- `MEILI-P010` (Warning): top recurring failure reasons from task error payloads.

---

## Data model & plumbing changes

- Extend the analysis pipeline to optionally include:
  - `InstanceLaunchConfig` (parsed from TOML)
  - `probe_results` (if `--probe-search`) stored in report metadata
  - configurable `sample_documents` count
- Ensure exporters (JSON/Markdown/Web/SARIF) gracefully handle additional metadata.

---

## Testing plan

- Add unit tests for TOML parsing and instance-config findings.
- Add analyzer tests for new Schema/Document/Performance findings.
- Add mock live-collector tests for `--probe-search` behavior (mock `search()` results).

---

## Rollout plan

1. Implement CLI + data plumbing for optional inputs (config toml, sample-documents, probe-search).
2. Add instance-config analyzer and 2–3 high-value findings first (`I001`, `I004`, `I003`).
3. Add index/document improvements (primary key, sortable types, arrays-of-objects).
4. Add task backlog + error clustering.
5. Iterate on thresholds based on real-world feedback.
