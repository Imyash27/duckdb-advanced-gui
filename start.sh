#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════╗
# ║  DuckDB Advanced GUI — Interactive Launcher             ║
# ║  Author: Yash Kanzariya                                 ║
# ║  Version: 2.0.0                                         ║
# ╚══════════════════════════════════════════════════════════╝
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DBS_FILE="$DIR/data/databases.json"
PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"

# ── Detect Python ─────────────────────────────────────────
VENV="$DIR/../venv"
if   [ -f "$VENV/bin/python" ];     then PY="$VENV/bin/python"
elif [ -f "$DIR/venv/bin/python" ]; then PY="$DIR/venv/bin/python"
elif command -v python3 &>/dev/null; then PY="python3"
elif command -v python  &>/dev/null; then PY="python"
else echo "❌  Python not found. Install Python 3.9+ and try again." && exit 1
fi

# Ensure dependencies
"$PY" -c "import flask" 2>/dev/null || "$PY" -m pip install flask werkzeug -q

mkdir -p "$DIR/data"

# ── Banner ────────────────────────────────────────────────
print_banner() {
  echo ""
  echo "  ╔══════════════════════════════════════════════════╗"
  echo "  ║   🦆  DuckDB Advanced GUI  v2.0.0               ║"
  echo "  ║       by Yash Kanzariya                          ║"
  echo "  ╚══════════════════════════════════════════════════╝"
  echo ""
}

# ── Get recent databases (pure bash, no jq needed) ────────
list_recent_dbs() {
  if [ ! -f "$DBS_FILE" ]; then return; fi
  "$PY" - <<'EOF' "$DBS_FILE"
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    dbs  = data.get("databases", [])
    active = data.get("active_id", "")
    for i, db in enumerate(dbs[:8], 1):
        mark = "●" if db["id"] == active else "○"
        print(f"  {i}. {mark} {db['name']}  —  {db['path']}")
except Exception:
    pass
EOF
}

get_db_path_by_index() {
  local idx="$1"
  "$PY" - <<EOF "$DBS_FILE"
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    dbs  = data.get("databases", [])
    print(dbs[${idx}-1]["path"])
except Exception:
    pass
EOF
}

# ── Database selection ────────────────────────────────────
select_database() {
  if [ -n "${DUCKDB_PATH:-}" ]; then
    echo "  Using: $DUCKDB_PATH"
    return
  fi

  print_banner
  local RECENT
  RECENT=$(list_recent_dbs 2>/dev/null || true)

  if [ -n "$RECENT" ]; then
    echo "  Recent databases:"
    echo "$RECENT"
    echo ""
    echo "  N  —  Enter new path"
    echo "  C  —  Create new empty database"
    echo "  Q  —  Quit"
    echo ""
    printf "  Select [1]: "
    read -r choice

    case "${choice:-1}" in
      [Qq])
        echo "  Goodbye." && exit 0 ;;
      [Nn])
        printf "  Database path: "
        read -r DUCKDB_PATH ;;
      [Cc])
        printf "  New database path (e.g. ~/mydb.duckdb): "
        read -r DUCKDB_PATH
        DUCKDB_PATH="${DUCKDB_PATH/#\~/$HOME}"
        echo "  → Will create new database: $DUCKDB_PATH" ;;
      [1-9])
        DUCKDB_PATH=$(get_db_path_by_index "$choice" 2>/dev/null || true)
        if [ -z "$DUCKDB_PATH" ]; then
          echo "  Invalid selection — enter path manually."
          printf "  Database path: "
          read -r DUCKDB_PATH
        fi ;;
      "")
        DUCKDB_PATH=$(get_db_path_by_index 1 2>/dev/null || true)
        if [ -z "$DUCKDB_PATH" ]; then
          printf "  Database path: "
          read -r DUCKDB_PATH
        fi ;;
      *)
        # Treat as a direct path
        DUCKDB_PATH="$choice" ;;
    esac
  else
    echo "  No recent databases found."
    echo ""
    printf "  Enter DuckDB file path (or press Enter for demo): "
    read -r DUCKDB_PATH
    if [ -z "$DUCKDB_PATH" ]; then
      DUCKDB_PATH="$DIR/../ioc_feeds.duckdb"
      echo "  → Using: $DUCKDB_PATH"
    fi
  fi

  # Expand tilde
  DUCKDB_PATH="${DUCKDB_PATH/#\~/$HOME}"
  export DUCKDB_PATH
}

# ── Advanced options ──────────────────────────────────────
show_advanced() {
  echo ""
  echo "  Advanced options (press Enter to accept defaults):"
  printf "  Port [${PORT}]: "
  read -r _port
  [ -n "$_port" ] && PORT="$_port"

  printf "  Host [${HOST}] (use 127.0.0.1 to restrict to local only): "
  read -r _host
  [ -n "$_host" ] && HOST="$_host"

  printf "  Enable basic auth? [y/N]: "
  read -r _auth
  if [[ "$_auth" =~ ^[Yy]$ ]]; then
    printf "  Username: "
    read -r _user
    printf "  Password: "
    read -rs _pass
    echo ""
    export DUCK_USER="$_user"
    export DUCK_PASS="$_pass"
  fi
}

# ── Run ───────────────────────────────────────────────────
select_database

# Optional: parse --advanced flag
for arg in "$@"; do
  [ "$arg" = "--advanced" ] && show_advanced
done

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   Starting...                                    ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "  URL      : http://localhost:${PORT}"
echo "  Database : ${DUCKDB_PATH:-[none]}"
echo "  Host     : ${HOST}"
echo "  Stop     : Ctrl+C"
echo ""
echo "  Tip: Add more databases from the + button in the UI"
echo ""

export PORT HOST
exec "$PY" "$DIR/app.py"
