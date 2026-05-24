# 🦆 DuckDB Advanced GUI

<div align="center">

**A powerful, self-hosted web GUI for DuckDB — built for analysts, data engineers, and developers.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://python.org)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.x-yellow?logo=duckdb)](https://duckdb.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-green?logo=flask)](https://flask.palletsprojects.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)
[![Author](https://img.shields.io/badge/Author-Yash%20Kanzariya-orange)](https://github.com/yashkanzariya)

</div>

---

## ✨ Features

### 🗄️ Multi-Database Management
- **Switch between multiple DuckDB databases** without restarting
- Interactive launcher with recent-database memory
- Open existing databases or create new ones from the UI
- Per-database connection history and state

### 📝 SQL Editor
- **CodeMirror syntax highlighting** with SQL auto-complete (table + column names)
- **Multi-tab editor** — work on multiple queries simultaneously
- **Persistent query history** (last 300 queries with timing and row counts)
- Saved/bookmarked queries across sessions
- `Ctrl+Enter` to run · `Ctrl+/` to comment · Tab indent
- EXPLAIN and EXPLAIN ANALYZE with formatted output
- SQL formatter / beautifier
- Export results as CSV or JSON

### 🔍 Data Browser
- Paginated table view with configurable page sizes
- **Column-level search / filter** with ILIKE matching
- **Click-column-header sort** (ASC / DESC)
- **Inline row editing** — edit, add, and delete rows with a modal form
- Multi-format export: CSV · JSON · JSONL · Parquet (ZSTD compressed)

### 🏗️ Schema Manager
- Full schema tree: Tables · Views · Indexes · Sequences
- **Column statistics**: min, max, avg, distinct count, null count, string lengths
- Index and constraint viewer
- DDL viewer with one-click copy
- **Visual table builder** — create tables without writing SQL
- **Add column, create index, drop table** — all from the UI
- Alter table operations

### ⚡ Performance & Maintenance
- **VACUUM · CHECKPOINT · FORCE CHECKPOINT · ANALYZE** — one-click operations
- EXPLAIN ANALYZE panel for query profiling
- DB file size tracker (before/after maintenance)
- **All DuckDB settings** — searchable, editable in-place
- Table row counts and estimated sizes

### 📥 Import / Export
- **Drag-and-drop file upload**: CSV · TSV · JSON · JSONL · Parquet
- Import modes: **Create / Append / Replace**
- CSV options: custom delimiter, header toggle
- Export any table or custom SQL result
- Formats: CSV · JSON · JSONL · Parquet (ZSTD)

### 🧩 Extensions Manager
- View all DuckDB extensions (loaded / installed / available)
- **Install and load extensions** from the UI
- Version and status badges

### 🔎 Functions Browser
- Search 300+ built-in DuckDB functions
- Filter by type: scalar · aggregate · table · macro
- Return type and description

### 🔒 Security
- Optional HTTP Basic Auth (set `DUCK_USER` + `DUCK_PASS` env vars)
- All SQL filter/sort parameters validated against actual schema columns
- Table names validated against `SHOW TABLES` before use
- Extension names whitelisted via regex
- Blocked DDL patterns (COPY TO, EXPORT DATABASE) on unsafe endpoints
- No stack traces exposed to clients in production mode
- Upload file type validation (extension + size limits)

---

## 🚀 Quick Start

### Option 1 — Interactive launcher (recommended)

```bash
git clone https://github.com/yashkanzariya/duckdb-advanced-gui
cd duckdb-advanced-gui

pip install -r requirements.txt   # or: python -m pip install flask werkzeug duckdb
chmod +x start.sh
./start.sh
```

The launcher will prompt you to choose or enter a DuckDB file path, then open the GUI at **http://localhost:5000**.

### Option 2 — Direct with env var

```bash
DUCKDB_PATH=/path/to/your.duckdb python app.py
```

### Option 3 — Custom port / host

```bash
PORT=8080 HOST=127.0.0.1 DUCKDB_PATH=mydb.duckdb ./start.sh
```

### Option 4 — Advanced options (auth, host binding)

```bash
./start.sh --advanced
```

---

## 📋 Requirements

| Dependency | Version |
|-----------|---------|
| Python    | 3.9+    |
| DuckDB    | 1.0+    |
| Flask     | 3.x     |
| Werkzeug  | 3.x     |

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

All configuration is via environment variables:

| Variable       | Default         | Description |
|---------------|-----------------|-------------|
| `DUCKDB_PATH` | *(prompted)*    | Path to DuckDB database file |
| `PORT`        | `5000`          | HTTP port |
| `HOST`        | `0.0.0.0`       | Bind address (`127.0.0.1` for local-only) |
| `DUCK_USER`   | *(none)*        | Enable basic auth — username |
| `DUCK_PASS`   | *(none)*        | Enable basic auth — password |
| `DUCK_DEBUG`  | `0`             | Set to `1` for debug mode (shows tracebacks) |

---

## 🔒 Security Notes

This tool is designed for **local development and trusted internal networks**.

For production or public exposure:
- Always set `DUCK_USER` + `DUCK_PASS` for basic auth
- Bind to `127.0.0.1` (`HOST=127.0.0.1`) and use a reverse proxy (nginx/caddy) with TLS
- Consider running inside Docker with network isolation
- See [SECURITY.md](SECURITY.md) for the full security policy

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md).

---

## 👤 Author

**Yash Kanzariya**  
[GitHub](https://github.com/yashkanzariya) · [Email](mailto:yashkanzariya50@gmail.com)

---

## 📄 License

[MIT](LICENSE) © 2026 Yash Kanzariya
