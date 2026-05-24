# Changelog

All notable changes to **DuckDB Advanced GUI** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.1.0] — 2026-05-24

### Added — Live Monitor & Dashboards

- **📡 Monitor tab** — Grafana-style live performance monitoring, auto-refreshes every 2–30 s (configurable):
  - Stat cards: total queries, avg/P95/max latency, error rate, DB file size, queries in last 60 s
  - **Query Latency** line chart (60-second rolling window)
  - **Queries/second** bar chart
  - **SQL Type Mix** doughnut chart (SELECT vs INSERT vs UPDATE vs …)
  - **Error Rate** bar chart
  - Live query log table (last 20 queries with type, timing, status, SQL preview)
  - In-memory ring buffer (2 000 events) with zero disk I/O — resets on restart by design
- **📊 Dashboards tab** — Custom chart panel builder (Grafana-lite):
  - **8 built-in starter panels** for IOC data (⚡ Load Starter Panels button)
  - **8 chart types**: Bar · Line · Area · Pie · Doughnut · Scatter · Stat card · Table
  - **6 colour palettes**: Indigo · Warm · Cool · Rainbow · Monochrome · Traffic light
  - **Live preview** before saving — run SQL and see the chart instantly in the modal
  - Auto-refresh per panel (10 s / 30 s / 1 min / 5 min / manual)
  - One-click suggestion chips for common IOC queries
  - Edit · Refresh · Delete per panel
  - Panels persisted to `data/panels.json`
- **`/api/metrics/live`** — real-time metrics endpoint (60-bucket time series)
- **`/api/chart/query`** — SQL-to-chart data endpoint
- **`/api/panels`** GET/POST · **`/api/panels/<id>`** DELETE
- **`/api/panels/reset`** — restore built-in starter panels
- Chart.js 4.4 loaded from CDN for all visualisations

---

## [2.0.0] — 2026-05-24

### Added
- **Multi-database support** — switch between multiple DuckDB files without restarting; database registry persisted in `data/databases.json`
- **Interactive launcher** (`start.sh`) — prompts for database selection, shows recent databases, supports `--advanced` flag for auth/host config
- **HTTP Basic Auth** — enable by setting `DUCK_USER` + `DUCK_PASS` environment variables
- **Functions browser** tab — search 300+ built-in DuckDB functions with type and return info
- **Extensions manager** — install, load, and update DuckDB extensions from the UI
- **Visual table builder** in Import/Export tab — create tables with column type picker without writing SQL
- **Column statistics** in Schema tab — per-column min/max/avg/distinct/nulls/string-length analysis
- **Draggable editor/result splitter** — resize the SQL editor and result pane interactively
- **Constraints viewer** in Schema tab
- **Sequences viewer** in schema tree
- Multi-statement execution — run multiple `;`-separated statements in one go
- Add Column modal with NOT NULL and DEFAULT support
- Create Index modal with UNIQUE support
- Drop Table with confirmation dialog
- Query history per-entry delete
- `DUCK_DEBUG` env var for debug mode (tracebacks only visible server-side by default)
- `HOST` env var to control bind address

### Security
- All filter/sort column names validated against actual schema before use
- Table names validated with `validate_table_exists()` before every data operation
- Extension names validated via regex `[a-zA-Z][a-zA-Z0-9_]*`
- Setting names validated against `duckdb_settings()` before SET
- Blocked dangerous DDL patterns on the `/api/ddl` endpoint
- Row limit hard-capped at 10,000 per query
- Upload size capped at 200 MB; file extensions whitelist-checked
- Error responses never expose stack traces in production
- Atomic JSON writes (write-then-rename) for history/saved/databases files
- Full-table DELETE blocked — `WHERE` clause always required

### Changed
- Complete backend rewrite with `safe_ident()` and `validate_table_exists()` guards on all routes
- `err_resp()` helper centralises error serialisation (no raw `traceback.format_exc()` to client)
- `COPY … TO` in export uses parameterised path (`?`) not string interpolation
- Filter queries use parameterised `ILIKE ?` instead of f-string interpolation
- JSON files use atomic write (temp-then-replace) to prevent corruption

---

## [1.0.0] — 2026-05-23

### Added
- Initial release
- Dashboard with IOC stats, bar charts, feed sync status
- SQL Editor with CodeMirror, history, saved queries
- Data Browser with filter, sort, pagination, CSV export
- Schema viewer (columns, DDL)
- Performance tab (VACUUM, CHECKPOINT, ANALYZE, settings)
- Import: CSV, JSON, Parquet
- Export: CSV, JSON, JSONL, Parquet
- Extensions list
