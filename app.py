"""
DuckDB Advanced GUI — Flask Backend
Author : Yash Kanzariya
License: MIT
Version: 2.0.0

Security-hardened REST API for full DuckDB introspection, editing,
multi-database management, performance tuning, and import/export.
"""
import os
import re
import json
import time
import uuid
import logging
import decimal
import tempfile
import threading
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file, Response, abort

# ─── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # 200 MB upload cap
app.config["JSON_SORT_KEYS"]     = False

DEBUG = os.environ.get("DUCK_DEBUG", "0") == "1"

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("duckdb-gui")

BASE      = Path(__file__).parent
DATA      = BASE / "data"
DATA.mkdir(exist_ok=True)

HISTORY_F = DATA / "history.json"
SAVED_F   = DATA / "saved.json"
DBS_F     = DATA / "databases.json"

# Allowed file extensions for import
ALLOWED_IMPORT_EXT = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".parquet"}
# Max table/index/column name length
MAX_IDENT_LEN      = 128
# Optional basic-auth (set DUCK_USER + DUCK_PASS env vars to enable)
AUTH_USER = os.environ.get("DUCK_USER", "")
AUTH_PASS = os.environ.get("DUCK_PASS", "")

_lock = threading.Lock()

# ─── Security helpers ──────────────────────────────────────────────────────────

def require_auth(f):
    """Optional basic-auth guard — only active when DUCK_USER/PASS are set."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not AUTH_USER:           # auth disabled
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or auth.username != AUTH_USER or auth.password != AUTH_PASS:
            return Response("Authentication required", 401,
                            {"WWW-Authenticate": 'Basic realm="DuckDB GUI"'})
        return f(*args, **kwargs)
    return decorated

app.before_request(require_auth(lambda: None).__wrapped__ if AUTH_USER else lambda: None)

_SAFE_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_ $]*$')

def safe_ident(name: str, context: str = "identifier") -> str:
    """Validate and return a safe SQL identifier or raise ValueError."""
    if not name or len(name) > MAX_IDENT_LEN:
        raise ValueError(f"Invalid {context}: empty or too long")
    if not _SAFE_IDENT.match(name):
        raise ValueError(
            f"Invalid {context} '{name}': only letters, digits, _ and $ allowed"
        )
    return name

def validate_table_exists(con, name: str) -> str:
    """Confirm the table (or view) exists in the current DB."""
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    if name not in tables:
        raise ValueError(f"Table or view '{name}' does not exist")
    return name

def validate_sort_dir(d: str) -> str:
    if d.upper() not in ("ASC", "DESC"):
        raise ValueError("sort direction must be ASC or DESC")
    return d.upper()

def validate_db_path(path_str: str) -> Path:
    """Resolve and sanity-check a DuckDB file path."""
    p = Path(path_str).expanduser().resolve()
    if p.suffix not in (".duckdb", ".db", ".ddb", ""):
        raise ValueError(f"File '{p.name}' does not look like a DuckDB database")
    return p

# ─── Serialisation ────────────────────────────────────────────────────────────

def ser(v):
    if isinstance(v, (datetime, date)):  return v.isoformat()
    if isinstance(v, timedelta):         return str(v)
    if isinstance(v, decimal.Decimal):   return float(v)
    if isinstance(v, (list, dict)):      return str(v)
    return v

def ser_row(row):
    return [ser(v) for v in row]

def jresp(data, status=200):
    return Response(
        json.dumps(data, default=str, ensure_ascii=False),
        status=status,
        content_type="application/json; charset=utf-8",
    )

def err_resp(msg: str, status: int = 400, exc: Exception = None) -> Response:
    payload = {"error": msg}
    if DEBUG and exc:
        payload["detail"] = traceback.format_exc()
    log.warning("API error [%d]: %s", status, msg)
    return jresp(payload, status)

# ─── Utility ──────────────────────────────────────────────────────────────────

def hs(n: int) -> str:
    n = int(n or 0)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {u}"
        n //= 1024
    return f"{n:.1f} PB"

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default

def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)           # atomic on POSIX

def add_history(sql: str, dur: float, rows: int, error: str = None) -> None:
    with _lock:
        h = load_json(HISTORY_F, [])
        h.insert(0, {
            "id":    int(time.time() * 1000),
            "sql":   sql[:4000],        # cap size
            "dur":   round(dur, 4),
            "rows":  rows,
            "error": error,
            "ts":    datetime.now().isoformat(),
        })
        save_json(HISTORY_F, h[:300])

# ─── Multi-database management ────────────────────────────────────────────────

def load_dbs() -> dict:
    default = {"active_id": None, "databases": []}
    return load_json(DBS_F, default)

def save_dbs(data: dict) -> None:
    save_json(DBS_F, data)

def get_active_db_path() -> Path:
    cfg  = load_dbs()
    aid  = cfg.get("active_id")
    dbs  = cfg.get("databases", [])
    if aid:
        db = next((d for d in dbs if d["id"] == aid), None)
        if db:
            return Path(db["path"]).resolve()
    # Fall back to env / first in list
    env = os.environ.get("DUCKDB_PATH", "")
    if env:
        return Path(env).resolve()
    if dbs:
        return Path(dbs[0]["path"]).resolve()
    raise RuntimeError("No database configured. Add one via the UI or set DUCKDB_PATH.")

def get_con(read_only: bool = False):
    import duckdb
    path = get_active_db_path()
    return duckdb.connect(str(path), read_only=read_only)

# ─── Boot: register env DB ────────────────────────────────────────────────────

def _register_env_db() -> None:
    env = os.environ.get("DUCKDB_PATH", "")
    if not env:
        return
    cfg  = load_dbs()
    path = Path(env).resolve()
    # Only add if not already present
    if not any(Path(d["path"]).resolve() == path for d in cfg["databases"]):
        entry = {
            "id":        str(uuid.uuid4()),
            "name":      path.stem,
            "path":      str(path),
            "added":     datetime.now().isoformat(),
            "last_used": datetime.now().isoformat(),
        }
        cfg["databases"].insert(0, entry)
        if cfg["active_id"] is None:
            cfg["active_id"] = entry["id"]
        save_dbs(cfg)

# ─── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    try:
        db_path = str(get_active_db_path())
    except RuntimeError:
        db_path = "No database selected"
    return render_template("index.html", db_path=db_path, version="2.0.0",
                           author="Yash Kanzariya")

# ─── Database management endpoints ────────────────────────────────────────────

@app.route("/api/databases")
def api_db_list():
    cfg = load_dbs()
    return jresp(cfg)

@app.route("/api/databases", methods=["POST"])
def api_db_add():
    body   = request.get_json(silent=True) or {}
    raw    = body.get("path", "").strip()
    name   = body.get("name", "").strip()
    create = body.get("create", False)      # create if not exists
    if not raw:
        return err_resp("path required")
    try:
        path = validate_db_path(raw)
    except ValueError as e:
        return err_resp(str(e))
    if not create and not path.exists():
        return err_resp(f"File not found: {path}")
    if not name:
        name = path.stem
    cfg = load_dbs()
    # Duplicate check
    if any(Path(d["path"]).resolve() == path for d in cfg["databases"]):
        return err_resp("This database is already in the list")
    entry = {
        "id":        str(uuid.uuid4()),
        "name":      name[:80],
        "path":      str(path),
        "added":     datetime.now().isoformat(),
        "last_used": datetime.now().isoformat(),
    }
    cfg["databases"].insert(0, entry)
    if cfg["active_id"] is None:
        cfg["active_id"] = entry["id"]
    save_dbs(cfg)
    return jresp({"ok": True, "id": entry["id"], "entry": entry})

@app.route("/api/databases/<db_id>", methods=["DELETE"])
def api_db_remove(db_id):
    cfg = load_dbs()
    cfg["databases"] = [d for d in cfg["databases"] if d["id"] != db_id]
    if cfg["active_id"] == db_id:
        cfg["active_id"] = cfg["databases"][0]["id"] if cfg["databases"] else None
    save_dbs(cfg)
    return jresp({"ok": True})

@app.route("/api/databases/<db_id>/switch", methods=["POST"])
def api_db_switch(db_id):
    cfg = load_dbs()
    db  = next((d for d in cfg["databases"] if d["id"] == db_id), None)
    if not db:
        return err_resp("Database not found", 404)
    cfg["active_id"] = db_id
    db["last_used"]  = datetime.now().isoformat()
    save_dbs(cfg)
    return jresp({"ok": True, "path": db["path"], "name": db["name"]})

@app.route("/api/databases/<db_id>", methods=["PATCH"])
def api_db_rename(db_id):
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()[:80]
    if not name:
        return err_resp("name required")
    cfg = load_dbs()
    for d in cfg["databases"]:
        if d["id"] == db_id:
            d["name"] = name
            break
    save_dbs(cfg)
    return jresp({"ok": True})

# ─── Info ─────────────────────────────────────────────────────────────────────

@app.route("/api/info")
def api_info():
    try:
        con     = get_con()
        version = con.execute("SELECT version()").fetchone()[0]
        db_path = get_active_db_path()
        db_size = db_path.stat().st_size if db_path.exists() else 0
        tables  = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        try:    threads = con.execute("SELECT current_setting('threads')").fetchone()[0]
        except: threads = "?"
        try:    mem = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
        except: mem = "?"
        con.close()
        return jresp({"version": version, "db_path": str(db_path),
                      "db_size": db_size, "db_size_human": hs(db_size),
                      "table_count": len(tables), "threads": threads,
                      "memory_limit": mem})
    except Exception as e:
        return err_resp(str(e), 500, e)

# ─── Schema tree ──────────────────────────────────────────────────────────────

@app.route("/api/schema")
def api_schema():
    try:
        con = get_con()
        tables = []
        for row in con.execute(
            "SELECT table_name, estimated_size, column_count, has_primary_key, sql "
            "FROM duckdb_tables() WHERE internal=false ORDER BY table_name"
        ).fetchall():
            tname = row[0]
            try:    count = con.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
            except: count = 0
            cols = con.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM duckdb_columns() WHERE table_name=? ORDER BY column_index", [tname]
            ).fetchall()
            tables.append({"name": tname, "count": count, "est_size": row[1],
                           "col_count": row[2], "has_pk": row[3], "ddl": row[4] or "",
                           "columns": [{"name": c[0], "type": c[1], "nullable": c[2],
                                        "default": c[3]} for c in cols]})
        views = []
        for row in con.execute(
            "SELECT view_name, sql FROM duckdb_views() WHERE internal=false ORDER BY view_name"
        ).fetchall():
            views.append({"name": row[0], "sql": row[1] or ""})

        indexes = []
        for row in con.execute(
            "SELECT index_name, table_name, is_unique, is_primary, sql "
            "FROM duckdb_indexes() ORDER BY index_name"
        ).fetchall():
            indexes.append({"name": row[0], "table": row[1], "unique": row[2],
                            "primary": row[3], "sql": row[4] or ""})

        seqs = []
        for row in con.execute(
            "SELECT sequence_name, start_value, increment_by, min_value, max_value, "
            "cycle, last_value FROM duckdb_sequences() ORDER BY sequence_name"
        ).fetchall():
            seqs.append({"name": row[0], "start": row[1], "incr": row[2],
                         "min": row[3], "max": row[4], "cycle": row[5], "last": row[6]})
        con.close()
        return jresp({"tables": tables, "views": views,
                      "indexes": indexes, "sequences": seqs})
    except Exception as e:
        return err_resp(str(e), 500, e)

# ─── Table detail ─────────────────────────────────────────────────────────────

@app.route("/api/schema/table/<name>")
def api_table_schema(name):
    try:
        safe_ident(name, "table name")
        con = get_con()
        validate_table_exists(con, name)
        cols = con.execute(
            "SELECT column_name, data_type, is_nullable, column_default, "
            "numeric_precision, numeric_scale "
            "FROM duckdb_columns() WHERE table_name=? ORDER BY column_index", [name]
        ).fetchall()
        try:    count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except: count = 0

        try:
            row = con.execute("SELECT sql FROM duckdb_tables() WHERE table_name=?", [name]).fetchone()
            ddl = row[0] if row else ""
        except: ddl = ""

        idxs = []
        try:
            for r in con.execute(
                "SELECT index_name, is_unique, is_primary, sql "
                "FROM duckdb_indexes() WHERE table_name=?", [name]
            ).fetchall():
                idxs.append({"name": r[0], "unique": r[1], "primary": r[2], "sql": r[3] or ""})
        except: pass

        cons = []
        try:
            for r in con.execute(
                "SELECT constraint_type, constraint_text, constraint_column_names "
                "FROM duckdb_constraints() WHERE table_name=?", [name]
            ).fetchall():
                cons.append({"type": r[0], "text": r[1], "columns": r[2]})
        except: pass

        col_stats = []
        for c in cols:
            cname, ctype = c[0], c[1].upper()
            stat = {"column": cname, "type": c[1]}
            try:
                if any(t in ctype for t in [
                    "INT","FLOAT","DOUBLE","DECIMAL","NUMERIC","REAL",
                    "BIGINT","TINYINT","SMALLINT","HUGEINT","UBIGINT"
                ]):
                    r = con.execute(
                        f'SELECT MIN("{cname}"), MAX("{cname}"), '
                        f'AVG("{cname}"), COUNT(DISTINCT "{cname}"), '
                        f'COUNT(*) FILTER (WHERE "{cname}" IS NULL) FROM "{name}"'
                    ).fetchone()
                    stat.update({"min": ser(r[0]), "max": ser(r[1]),
                                 "avg": round(float(r[2]), 4) if r[2] is not None else None,
                                 "distinct": r[3], "nulls": r[4]})
                elif any(t in ctype for t in ["VARCHAR","TEXT","CHAR","STRING"]):
                    r = con.execute(
                        f'SELECT COUNT(DISTINCT "{cname}"), '
                        f'COUNT(*) FILTER (WHERE "{cname}" IS NULL), '
                        f'MIN(LENGTH("{cname}")), MAX(LENGTH("{cname}")) FROM "{name}"'
                    ).fetchone()
                    stat.update({"distinct": r[0], "nulls": r[1],
                                 "min_len": r[2], "max_len": r[3]})
                elif "BOOL" in ctype:
                    r = con.execute(
                        f'SELECT COUNT(*) FILTER (WHERE "{cname}"=true), '
                        f'COUNT(*) FILTER (WHERE "{cname}"=false), '
                        f'COUNT(*) FILTER (WHERE "{cname}" IS NULL) FROM "{name}"'
                    ).fetchone()
                    stat.update({"true_count": r[0], "false_count": r[1], "nulls": r[2]})
                elif any(t in ctype for t in ["DATE","TIMESTAMP","TIME"]):
                    r = con.execute(
                        f'SELECT MIN("{cname}"), MAX("{cname}"), '
                        f'COUNT(DISTINCT "{cname}"), '
                        f'COUNT(*) FILTER (WHERE "{cname}" IS NULL) FROM "{name}"'
                    ).fetchone()
                    stat.update({"min": ser(r[0]), "max": ser(r[1]),
                                 "distinct": r[2], "nulls": r[3]})
                else:
                    r = con.execute(
                        f'SELECT COUNT(DISTINCT "{cname}"), '
                        f'COUNT(*) FILTER (WHERE "{cname}" IS NULL) FROM "{name}"'
                    ).fetchone()
                    stat.update({"distinct": r[0], "nulls": r[1]})
            except: pass
            col_stats.append(stat)

        con.close()
        return jresp({
            "name": name, "count": count, "ddl": ddl or f'-- DDL not available for "{name}"',
            "columns": [{"name": c[0], "type": c[1], "nullable": c[2],
                         "default": c[3], "num_precision": c[4], "num_scale": c[5]}
                        for c in cols],
            "indexes": idxs, "constraints": cons, "col_stats": col_stats,
        })
    except ValueError as e:
        return err_resp(str(e), 400)
    except Exception as e:
        return err_resp(str(e), 500, e)

# ─── Query ────────────────────────────────────────────────────────────────────

@app.route("/api/query", methods=["POST"])
def api_query():
    body  = request.get_json(silent=True) or {}
    sql   = body.get("sql", "").strip()
    limit = min(int(body.get("limit", 1000)), 10_000)   # hard cap
    if not sql:
        return err_resp("Empty query")
    t0 = time.time()
    try:
        con = get_con()
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
        rel   = None
        for stmt in stmts:
            rel = con.execute(stmt)
        dur = time.time() - t0
        if rel and rel.description:
            cols = [d[0] for d in rel.description]
            rows = [ser_row(r) for r in rel.fetchmany(limit)]
            add_history(sql, dur, len(rows))
            con.close()
            return jresp({"columns": cols, "rows": rows, "count": len(rows),
                          "truncated": len(rows) == limit,
                          "duration": round(dur, 4), "affected": None})
        dur = time.time() - t0
        add_history(sql, dur, 0)
        con.close()
        return jresp({"columns": [], "rows": [], "count": 0,
                      "duration": round(dur, 4),
                      "affected": getattr(rel, "rowcount", 0)})
    except Exception as e:
        dur = time.time() - t0
        add_history(sql, dur, 0, str(e))
        return err_resp(str(e), 400, e)

# ─── EXPLAIN ──────────────────────────────────────────────────────────────────

@app.route("/api/explain", methods=["POST"])
def api_explain():
    body    = request.get_json(silent=True) or {}
    sql     = body.get("sql", "").strip()
    analyze = body.get("analyze", True)
    if not sql:
        return err_resp("Empty query")
    try:
        con  = get_con()
        kw   = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
        rel  = con.execute(f"{kw} {sql}")
        rows = rel.fetchall()
        con.close()
        return jresp({"plan": "\n".join(str(r[0]) for r in rows)})
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── Paginated browse ─────────────────────────────────────────────────────────

@app.route("/api/table/<name>")
def api_table(name):
    try:
        safe_ident(name, "table name")
        offset   = max(0, int(request.args.get("offset", 0)))
        limit    = min(max(1, int(request.args.get("limit", 100))), 1000)
        sort_col = request.args.get("sort", "")
        sort_dir = validate_sort_dir(request.args.get("dir", "ASC"))
        fc       = request.args.get("filter_col", "")
        fv       = request.args.get("filter_val", "")
        con      = get_con()
        validate_table_exists(con, name)

        # Validate sort column against actual columns
        if sort_col:
            actual_cols = {r[0] for r in con.execute(
                "SELECT column_name FROM duckdb_columns() WHERE table_name=?", [name]
            ).fetchall()}
            if sort_col not in actual_cols:
                sort_col = ""

        # Filter: use parameterised ILIKE where possible
        where_sql  = ""
        where_vals = []
        if fc and fv:
            # Validate filter column
            actual_cols = {r[0] for r in con.execute(
                "SELECT column_name FROM duckdb_columns() WHERE table_name=?", [name]
            ).fetchall()}
            if fc in actual_cols:
                where_sql  = f'WHERE CAST("{fc}" AS VARCHAR) ILIKE ?'
                where_vals = [f"%{fv}%"]

        order = f'ORDER BY "{sort_col}" {sort_dir}' if sort_col else ""
        total = con.execute(
            f'SELECT COUNT(*) FROM "{name}" {where_sql}', where_vals
        ).fetchone()[0]
        rel   = con.execute(
            f'SELECT * FROM "{name}" {where_sql} {order} LIMIT ? OFFSET ?',
            where_vals + [limit, offset]
        )
        cols  = [d[0] for d in rel.description]
        rows  = [ser_row(r) for r in rel.fetchall()]
        con.close()
        return jresp({"columns": cols, "rows": rows, "total": total})
    except ValueError as e:
        return err_resp(str(e), 400)
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── CRUD ─────────────────────────────────────────────────────────────────────

@app.route("/api/table/<name>/insert", methods=["POST"])
def api_insert(name):
    try:
        safe_ident(name, "table name")
        data = (request.get_json(silent=True) or {}).get("data", {})
        if not data:
            return err_resp("No data provided")
        con = get_con()
        validate_table_exists(con, name)
        # Validate column names
        actual = {r[0] for r in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE table_name=?", [name]
        ).fetchall()}
        cols = [k for k in data if k in actual]
        if not cols:
            return err_resp("No valid columns provided")
        ph  = ", ".join("?" for _ in cols)
        col = ", ".join(f'"{c}"' for c in cols)
        con.execute(f'INSERT INTO "{name}" ({col}) VALUES ({ph})',
                    [data[c] for c in cols])
        con.close()
        return jresp({"ok": True})
    except ValueError as e:
        return err_resp(str(e))
    except Exception as e:
        return err_resp(str(e), 400, e)

@app.route("/api/table/<name>/update", methods=["POST"])
def api_update(name):
    try:
        safe_ident(name, "table name")
        body  = request.get_json(silent=True) or {}
        data  = body.get("data", {})
        where = body.get("where", {})
        if not data or not where:
            return err_resp("data and where required")
        con = get_con()
        validate_table_exists(con, name)
        actual = {r[0] for r in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE table_name=?", [name]
        ).fetchall()}
        set_cols   = [k for k in data  if k in actual]
        where_cols = [k for k in where if k in actual]
        if not set_cols:
            return err_resp("No valid set columns")
        sets = ", ".join(f'"{k}" = ?' for k in set_cols)
        cond = " AND ".join(f'"{k}" = ?' for k in where_cols)
        vals = [data[c] for c in set_cols] + [where[c] for c in where_cols]
        con.execute(f'UPDATE "{name}" SET {sets} WHERE {cond}', vals)
        con.close()
        return jresp({"ok": True})
    except ValueError as e:
        return err_resp(str(e))
    except Exception as e:
        return err_resp(str(e), 400, e)

@app.route("/api/table/<name>/delete", methods=["POST"])
def api_delete(name):
    try:
        safe_ident(name, "table name")
        where = (request.get_json(silent=True) or {}).get("where", {})
        if not where:
            return err_resp("where required — full-table delete not permitted via this endpoint")
        con = get_con()
        validate_table_exists(con, name)
        actual = {r[0] for r in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE table_name=?", [name]
        ).fetchall()}
        where_cols = [k for k in where if k in actual]
        if not where_cols:
            return err_resp("No valid where columns")
        cond = " AND ".join(f'"{k}" = ?' for k in where_cols)
        con.execute(f'DELETE FROM "{name}" WHERE {cond}', [where[c] for c in where_cols])
        con.close()
        return jresp({"ok": True})
    except ValueError as e:
        return err_resp(str(e))
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── DDL execution ────────────────────────────────────────────────────────────

# Disallow dangerous DDL patterns
_BLOCKED_DDL = re.compile(
    r'\b(COPY\s+TO|EXPORT\s+DATABASE|IMPORT\s+DATABASE|LOAD\s+\S+)\b',
    re.IGNORECASE,
)

@app.route("/api/ddl", methods=["POST"])
def api_ddl():
    body = request.get_json(silent=True) or {}
    sql  = body.get("sql", "").strip()
    if not sql:
        return err_resp("Empty DDL")
    if _BLOCKED_DDL.search(sql):
        return err_resp("This DDL statement is not permitted via this endpoint")
    try:
        con = get_con()
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            con.execute(stmt)
        con.close()
        return jresp({"ok": True})
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── Settings ─────────────────────────────────────────────────────────────────

@app.route("/api/settings")
def api_settings():
    try:
        con  = get_con()
        rows = con.execute(
            "SELECT name, value, description, input_type, scope "
            "FROM duckdb_settings() ORDER BY name"
        ).fetchall()
        con.close()
        return jresp({"settings": [{"name": r[0], "value": r[1], "description": r[2],
                                     "type": r[3], "scope": r[4]} for r in rows]})
    except Exception as e:
        return err_resp(str(e), 500, e)

@app.route("/api/settings/set", methods=["POST"])
def api_settings_set():
    body  = request.get_json(silent=True) or {}
    name  = body.get("name", "").strip()
    value = body.get("value", "")
    if not name:
        return err_resp("name required")
    try:
        con = get_con()
        # Validate setting name against known settings
        known = {r[0] for r in con.execute("SELECT name FROM duckdb_settings()").fetchall()}
        if name not in known:
            con.close()
            return err_resp(f"Unknown setting: {name}")
        con.execute(f"SET {name} = ?", [str(value)])
        actual = con.execute(f"SELECT current_setting(?)", [name]).fetchone()[0]
        con.close()
        return jresp({"ok": True, "actual": actual})
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── Extensions ───────────────────────────────────────────────────────────────

_SAFE_EXT = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')

@app.route("/api/extensions")
def api_extensions():
    try:
        con  = get_con()
        rows = con.execute(
            "SELECT extension_name, loaded, installed, description, "
            "extension_version, install_mode "
            "FROM duckdb_extensions() ORDER BY extension_name"
        ).fetchall()
        con.close()
        return jresp({"extensions": [
            {"name": r[0], "loaded": r[1], "installed": r[2],
             "description": r[3], "version": r[4], "mode": r[5]} for r in rows
        ]})
    except Exception as e:
        return err_resp(str(e), 500, e)

@app.route("/api/extensions/action", methods=["POST"])
def api_ext_action():
    body   = request.get_json(silent=True) or {}
    name   = body.get("name", "").strip()
    action = body.get("action", "").strip()
    if not _SAFE_EXT.match(name):
        return err_resp("Invalid extension name")
    try:
        con = get_con()
        # Validate extension exists
        known = {r[0] for r in con.execute("SELECT extension_name FROM duckdb_extensions()").fetchall()}
        if action in ("load", "update") and name not in known:
            return err_resp(f"Unknown extension: {name}")
        if action == "install":
            con.execute(f"INSTALL {name}")
        elif action == "load":
            con.execute(f"LOAD {name}")
        elif action == "update":
            con.execute(f"UPDATE EXTENSIONS ({name})")
        else:
            return err_resp(f"Unknown action: {action}")
        con.close()
        return jresp({"ok": True})
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── Maintenance ──────────────────────────────────────────────────────────────

_ALLOWED_MAINT = {"vacuum", "checkpoint", "force_checkpoint", "analyze", "vacuum_analyze"}

@app.route("/api/maintenance", methods=["POST"])
def api_maintenance():
    body  = request.get_json(silent=True) or {}
    op    = body.get("op", "")
    table = body.get("table", "")
    if op not in _ALLOWED_MAINT:
        return err_resp(f"Unknown operation: {op}")
    t0 = time.time()
    try:
        con = get_con()
        if table:
            safe_ident(table, "table name")
            validate_table_exists(con, table)
        if op == "vacuum":           con.execute("VACUUM")
        elif op == "checkpoint":     con.execute("CHECKPOINT")
        elif op == "force_checkpoint": con.execute("FORCE CHECKPOINT")
        elif op == "analyze":        con.execute(f'ANALYZE "{table}"' if table else "ANALYZE")
        elif op == "vacuum_analyze": con.execute("VACUUM"); con.execute("ANALYZE")
        con.close()
        dur     = round(time.time() - t0, 3)
        db_path = get_active_db_path()
        db_size = db_path.stat().st_size if db_path.exists() else 0
        return jresp({"ok": True, "duration": dur,
                      "db_size": db_size, "db_size_human": hs(db_size)})
    except ValueError as e:
        return err_resp(str(e))
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── Performance stats ────────────────────────────────────────────────────────

@app.route("/api/perf")
def api_perf():
    try:
        con     = get_con()
        db_path = get_active_db_path()
        db_size = db_path.stat().st_size if db_path.exists() else 0
        t_stats = []
        for t in [r[0] for r in con.execute("SHOW TABLES").fetchall()]:
            try:
                rows = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                cols = len(con.execute(f'DESCRIBE "{t}"').fetchall())
                est  = con.execute(
                    "SELECT estimated_size FROM duckdb_tables() WHERE table_name=?", [t]
                ).fetchone()
                t_stats.append({"name": t, "rows": rows, "cols": cols,
                                "est_size": est[0] if est else 0})
            except: pass
        try:    threads = con.execute("SELECT current_setting('threads')").fetchone()[0]
        except: threads = "?"
        try:    mem = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
        except: mem = "?"
        try:    tmp_dir = con.execute("SELECT current_setting('temp_directory')").fetchone()[0]
        except: tmp_dir = ""
        con.close()
        return jresp({"db_size": db_size, "db_size_human": hs(db_size),
                      "table_stats": t_stats, "threads": threads,
                      "mem_limit": mem, "temp_dir": tmp_dir})
    except Exception as e:
        return err_resp(str(e), 500, e)

# ─── Functions & Types ────────────────────────────────────────────────────────

@app.route("/api/functions")
def api_functions():
    try:
        q   = request.args.get("q", "")[:100]   # cap length
        con = get_con()
        rows = con.execute(
            "SELECT function_name, function_type, description, return_type "
            "FROM duckdb_functions() WHERE function_name ILIKE ? ORDER BY function_name LIMIT 300",
            [f"%{q}%" if q else "%"]
        ).fetchall()
        con.close()
        return jresp({"functions": [{"name": r[0], "type": r[1],
                                      "desc": r[2], "return": r[3]} for r in rows]})
    except Exception as e:
        return err_resp(str(e), 500, e)

@app.route("/api/types")
def api_types():
    try:
        con  = get_con()
        rows = con.execute(
            "SELECT type_name, type_category, logical_type, type_size "
            "FROM duckdb_types() WHERE internal=false "
            "ORDER BY type_category, type_name"
        ).fetchall()
        con.close()
        return jresp({"types": [{"name": r[0], "category": r[1],
                                  "logical": r[2], "size": r[3]} for r in rows]})
    except Exception as e:
        return err_resp(str(e), 500, e)

# ─── History & Saved queries ──────────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    return jresp({"history": load_json(HISTORY_F, [])})

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    save_json(HISTORY_F, [])
    return jresp({"ok": True})

@app.route("/api/history/<int:hid>", methods=["DELETE"])
def api_history_del(hid):
    h = [x for x in load_json(HISTORY_F, []) if x.get("id") != hid]
    save_json(HISTORY_F, h)
    return jresp({"ok": True})

@app.route("/api/saved")
def api_saved_get():
    return jresp({"saved": load_json(SAVED_F, [])})

@app.route("/api/saved", methods=["POST"])
def api_saved_post():
    body  = request.get_json(silent=True) or {}
    name  = body.get("name", "Untitled")[:100]
    sql   = body.get("sql", "")[:4000]
    entry = {"id": int(time.time() * 1000), "name": name, "sql": sql,
             "ts": datetime.now().isoformat()}
    saved = load_json(SAVED_F, [])
    saved.insert(0, entry)
    save_json(SAVED_F, saved[:200])
    return jresp({"ok": True, "id": entry["id"]})

@app.route("/api/saved/<int:qid>", methods=["DELETE"])
def api_saved_del(qid):
    saved = [s for s in load_json(SAVED_F, []) if s.get("id") != qid]
    save_json(SAVED_F, saved)
    return jresp({"ok": True})

# ─── Export ───────────────────────────────────────────────────────────────────

_ALLOWED_EXPORT_FMT = {"csv", "parquet", "json", "jsonl"}

@app.route("/api/export/<name>")
def api_export(name):
    fmt     = request.args.get("fmt", "csv").lower()
    sql_override = request.args.get("sql", "").strip()
    if fmt not in _ALLOWED_EXPORT_FMT:
        return err_resp(f"Unsupported format: {fmt}. Use: {', '.join(_ALLOWED_EXPORT_FMT)}")
    try:
        safe_ident(name, "table/view name")
        con = get_con()
        if not sql_override:
            validate_table_exists(con, name)
        src    = f"({sql_override})" if sql_override else f'"{name}"'
        suffix = ".parquet" if fmt == "parquet" else f".{fmt}"
        mime   = {"csv": "text/csv", "parquet": "application/octet-stream",
                  "json": "application/json", "jsonl": "application/json"}[fmt]
        tmp    = tempfile.NamedTemporaryFile(suffix=suffix, delete=False,
                                             dir=str(DATA))
        tmp.close()
        try:
            if fmt == "csv":
                con.execute(f"COPY (SELECT * FROM {src}) TO ? (HEADER true, DELIMITER ',')", [tmp.name])
            elif fmt == "parquet":
                con.execute(f"COPY (SELECT * FROM {src}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [tmp.name])
            elif fmt == "json":
                con.execute(f"COPY (SELECT * FROM {src}) TO ? (FORMAT JSON, ARRAY true)", [tmp.name])
            elif fmt == "jsonl":
                con.execute(f"COPY (SELECT * FROM {src}) TO ? (FORMAT JSON, ARRAY false)", [tmp.name])
            con.close()
            dl_name = f"{name}.{'jsonl' if fmt=='jsonl' else fmt}"
            return send_file(tmp.name, as_attachment=True, download_name=dl_name, mimetype=mime)
        except Exception:
            try: os.unlink(tmp.name)
            except: pass
            raise
    except ValueError as e:
        return err_resp(str(e))
    except Exception as e:
        return err_resp(str(e), 400, e)

# ─── Import ───────────────────────────────────────────────────────────────────

@app.route("/api/import", methods=["POST"])
def api_import():
    tname  = request.form.get("table_name", "").strip()
    mode   = request.form.get("mode", "create")
    header = request.form.get("has_header", "true") == "true"
    delim  = request.form.get("delimiter", ",")
    if delim in ("\\t", "tab", "\t"):
        delim = "\t"
    elif len(delim) != 1:
        delim = ","
    if mode not in ("create", "append", "replace"):
        return err_resp(f"Invalid mode: {mode}")

    if "file" not in request.files:
        return err_resp("No file uploaded")

    f     = request.files["file"]
    fname = f.filename or "upload"
    # Validate extension
    ext   = Path(fname).suffix.lower()
    if ext not in ALLOWED_IMPORT_EXT:
        return err_resp(f"File type '{ext}' not allowed. Supported: {', '.join(ALLOWED_IMPORT_EXT)}")

    if not tname:
        # Derive table name from filename, sanitised
        stem   = Path(fname).stem
        tname  = re.sub(r'[^A-Za-z0-9_]', '_', stem)[:64]
        if not tname or tname[0].isdigit():
            tname = "imported_" + tname

    try:
        safe_ident(tname, "table name")
    except ValueError as e:
        return err_resp(str(e))

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=str(DATA))
    f.save(tmp.name); tmp.close()

    try:
        con = get_con()
        hdr = "true" if header else "false"

        def read_expr() -> str:
            if ext in (".csv", ".tsv"):
                d = "\t" if ext == ".tsv" else delim
                return f"read_csv_auto(?, header={hdr}, sep=?, ignore_errors=true)"
            elif ext == ".parquet":
                return "read_parquet(?)"
            elif ext in (".json", ".jsonl", ".ndjson"):
                return "read_json_auto(?)"
            raise ValueError(f"Unsupported: {ext}")

        expr   = read_expr()
        params = [tmp.name, delim] if ext in (".csv",) else [tmp.name]

        if mode == "create":
            con.execute(f'CREATE TABLE IF NOT EXISTS "{tname}" AS SELECT * FROM {expr}', params)
        elif mode == "replace":
            con.execute(f'DROP TABLE IF EXISTS "{tname}"')
            con.execute(f'CREATE TABLE "{tname}" AS SELECT * FROM {expr}', params)
        elif mode == "append":
            con.execute(f'INSERT INTO "{tname}" SELECT * FROM {expr}', params)

        count = con.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
        cols  = [d[0] for d in con.execute(f'DESCRIBE "{tname}"').fetchall()]
        con.close()
        return jresp({"ok": True, "table": tname, "count": count, "columns": cols})
    except ValueError as e:
        return err_resp(str(e))
    except Exception as e:
        return err_resp(str(e), 400, e)
    finally:
        try: os.unlink(tmp.name)
        except: pass

# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/api/dashboard")
def api_dashboard():
    try:
        con    = get_con()
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        t_stats = []
        for t in tables:
            try: t_stats.append({"name": t, "count": con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]})
            except: t_stats.append({"name": t, "count": 0})
        ioc = {}
        if "ioc_master" in tables:
            ioc["total"]      = con.execute("SELECT COUNT(*) FROM ioc_master").fetchone()[0]
            ioc["active"]     = con.execute("SELECT COUNT(*) FROM ioc_master WHERE is_active=true").fetchone()[0]
            ioc["by_type"]    = [list(r) for r in con.execute("SELECT ioc_type, COUNT(*) FROM ioc_master GROUP BY ioc_type ORDER BY 2 DESC").fetchall()]
            ioc["by_threat"]  = [list(r) for r in con.execute("SELECT threat_type, COUNT(*) FROM ioc_master GROUP BY threat_type ORDER BY 2 DESC LIMIT 10").fetchall()]
            ioc["top_src"]    = [list(r) for r in con.execute("SELECT source, COUNT(*) FROM ioc_master GROUP BY source ORDER BY 2 DESC LIMIT 10").fetchall()]
            ioc["score_dist"] = [list(r) for r in con.execute(
                "SELECT CASE WHEN score>=80 THEN 'High (80+)' WHEN score>=50 THEN 'Medium (50-79)' ELSE 'Low (<50)' END, COUNT(*) "
                "FROM ioc_master GROUP BY 1 ORDER BY 2 DESC").fetchall()]
            ioc["recent"] = [ser_row(r) for r in con.execute(
                "SELECT value, ioc_type, score, threat_type, source, last_seen "
                "FROM ioc_master ORDER BY last_seen DESC LIMIT 10").fetchall()]
        feeds = []
        if "sync_checkpoints" in tables:
            feeds = [ser_row(r) for r in con.execute(
                "SELECT feed_name, status, last_count, total_ingested, last_sync, error_msg "
                "FROM sync_checkpoints ORDER BY last_sync DESC NULLS LAST").fetchall()]
        db_path = get_active_db_path()
        db_size = db_path.stat().st_size if db_path.exists() else 0
        version = con.execute("SELECT version()").fetchone()[0]
        con.close()
        return jresp({"version": version, "db_size": db_size,
                      "db_size_human": hs(db_size), "table_stats": t_stats,
                      "ioc": ioc, "feeds": feeds})
    except Exception as e:
        return err_resp(str(e), 500, e)

# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _register_env_db()
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    log.info("DuckDB Advanced GUI v2.0.0 by Yash Kanzariya")
    log.info("Listening on http://%s:%d", host, port)
    try:
        db = get_active_db_path()
        log.info("Active database: %s", db)
    except RuntimeError:
        log.warning("No database configured — add one via the UI")
    app.run(host=host, port=port, debug=DEBUG)
