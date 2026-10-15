#!/usr/bin/env bash
#
# Run psql against the stack's Postgres (db service, hfm database), in either run mode.
#
#   ./scripts/sql-helper.sh                    open an interactive psql shell
#   ./scripts/sql-helper.sh --counts           row count of every table, largest first
#   ./scripts/sql-helper.sh --rows             contents of every table, values cut to 80 characters
#   ./scripts/sql-helper.sh -f <file> [args]   run a host SQL file (streamed in via stdin)
#   ./scripts/sql-helper.sh [psql-args...]     forward args to psql, e.g. -c "SELECT 1"
#   -h, --help                                 show this help
#
# Examples:
#   ./scripts/sql-helper.sh -c "SELECT month, status FROM reviews ORDER BY created_at;"
#   ./scripts/sql-helper.sh -f scripts/sql/all-tables.sql -v rows=1   # what --rows runs
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ALL_TABLES_SQL="$SCRIPT_DIR/sql/all-tables.sql"

case "${1:-}" in
  -h|--help) print_help; exit 0 ;;
  --counts)  shift; set -- -f "$ALL_TABLES_SQL" "$@" ;;
  --rows)    shift; set -- -f "$ALL_TABLES_SQL" -v rows=1 "$@" ;;
esac

# -f names a path on the host, not inside the container, so the file is streamed in via stdin
# rather than psql's own -f (which would resolve the path container-side).
SQL_FILE=""
if [[ "${1:-}" == "-f" || "${1:-}" == "--file" ]]; then
  SQL_FILE="${2:-}"
  if [[ -z "$SQL_FILE" || ! -f "$SQL_FILE" ]]; then
    echo "SQL file not found: ${SQL_FILE:-<none given>}" >&2
    exit 1
  fi
  shift 2
fi

require_env
load_env
require_docker

PSQL=(psql -U hfm -d hfm -v ON_ERROR_STOP=1)
if [[ -n "$SQL_FILE" ]]; then
  compose exec -T db "${PSQL[@]}" "$@" < "$SQL_FILE"
elif [[ $# -eq 0 ]]; then
  # An interactive shell needs a TTY, so -T is left off.
  compose exec db "${PSQL[@]}"
else
  compose exec -T db "${PSQL[@]}" "$@"
fi
