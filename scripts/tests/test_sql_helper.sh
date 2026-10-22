#!/usr/bin/env bash
# Verifies sql-helper.sh --rows: it dumps 20 rows of each table unless --limit names another
# count, the limit reaches the SQL as a psql variable, and a count that is not a whole number is
# refused naming the option.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$WORK/scripts/sql" "$WORK/backend" "$WORK/bin"
cp "$SCRIPTS_DIR/common.sh" "$SCRIPTS_DIR/sql-helper.sh" "$WORK/scripts/"
cp "$SCRIPTS_DIR/sql/all-tables.sql" "$WORK/scripts/sql/"
: > "$WORK/backend/.env"
# Stands in for Docker: prints the arguments it was called with and, for a compose call, what it
# was fed on stdin.
printf '#!/usr/bin/env bash\necho "docker $*"\n[ "$1" = compose ] && cat\nexit 0\n' \
  > "$WORK/bin/docker"
chmod +x "$WORK/bin/docker"
helper() { PATH="$WORK/bin:$PATH" bash "$WORK/scripts/sql-helper.sh" "$@" < /dev/null; }

out="$(helper --rows)"
grep -q -- '-v rows=1' <<< "$out" || fail "--rows did not select the row dump"
grep -q -- '-v limit=20' <<< "$out" || fail "--rows did not limit each table to 20 rows"
grep -q "LIMIT %s', cols.list, t.tablename, :limit" <<< "$out" \
  || fail "the SQL does not apply the limit variable"

out="$(helper --rows --limit 5)"
grep -q -- '-v limit=5' <<< "$out" || fail "--limit 5 did not reach psql"
grep -q -- '--limit' <<< "$out" && fail "--limit was forwarded to psql"

if err="$(helper --rows --limit five 2>&1)"; then fail "--limit five was accepted"; fi
grep -q -- '--limit' <<< "$err" || fail "the refusal does not name --limit: $err"

echo "test_sql_helper: all checks passed"
