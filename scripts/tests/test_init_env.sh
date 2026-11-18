#!/usr/bin/env bash
# Verifies init-env.sh: creates the three settings files from their examples, owner-readable
# only, with a generated database password and the database URL built from it; creates both empty
# registries, owner-readable only, and the budget from its example; keeps every existing file, yet
# creates a missing registry beside kept settings; and --force rewrites the settings files alone,
# never a registry or the budget.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$WORK/scripts/lib" "$WORK/backend" "$WORK/config"
cp "$SCRIPTS_DIR/common.sh" "$SCRIPTS_DIR/init-env.sh" "$WORK/scripts/"
cp "$SCRIPTS_DIR"/lib/{settings-guard.sh,ec2.sh,stack-params.sh} "$WORK/scripts/lib/"
cp "$SCRIPTS_DIR"/lib/*.example.sh "$WORK/scripts/lib/"
printf 'currency: ILS\nlimits:\n  dining: 200\n' > "$WORK/config/budget.example.yaml"
init() { bash "$WORK/scripts/init-env.sh" "$@" 2>/dev/null; }
mode() { stat -c %a "$1"; }
value() { (source "$WORK/scripts/lib/stack-params.sh"; source "$1"; printf '%s' "${!2}"); }

init >/dev/null
for name in secrets params aws-config; do
  [ "$(mode "$WORK/scripts/lib/$name.sh")" = 600 ] || fail "$name.sh is not mode 600"
done
password="$(value "$WORK/scripts/lib/secrets.sh" POSTGRES_PASSWORD)"
[[ "$password" =~ ^[0-9a-f]{32}$ ]] || fail "the database password is not 32 hex characters"
[ "$(value "$WORK/scripts/lib/secrets.sh" DATABASE_URL)" \
  = "postgresql+psycopg://hfm:$password@127.0.0.1:5434/hfm" ] \
  || fail "the database URL is not built from the password and stack-params.sh"
[ -z "$(value "$WORK/scripts/lib/secrets.sh" LLM_API_KEY)" ] || fail "LLM_API_KEY is not blank"
for registry in card-agents.yaml card-agents.ec2.yaml; do
  [ "$(cat "$WORK/backend/$registry")" = "agents: []" ] || fail "empty $registry not created"
  [ "$(mode "$WORK/backend/$registry")" = 600 ] || fail "$registry is not mode 600"
done
grep -q 'dining: 200' "$WORK/config/budget.yaml" || fail "budget not created from the example"

printf 'export GOOGLE_CLIENT_ID="kept"\n' > "$WORK/scripts/lib/params.sh"
rm "$WORK/backend/card-agents.yaml"
init >/dev/null || fail "refused to create the registry beside existing settings"
[ -f "$WORK/backend/card-agents.yaml" ] || fail "registry not created beside existing settings"
grep -q 'GOOGLE_CLIENT_ID="kept"' "$WORK/scripts/lib/params.sh" || fail "params.sh was overwritten"
[ "$(value "$WORK/scripts/lib/secrets.sh" POSTGRES_PASSWORD)" = "$password" ] \
  || fail "secrets.sh was overwritten"

printf 'currency: ILS\nlimits:\n  dining: 900\n' > "$WORK/config/budget.yaml"
printf 'agents: []\n# kept\n' > "$WORK/backend/card-agents.ec2.yaml"
init --force >/dev/null
grep -q 'GOOGLE_CLIENT_ID=""' "$WORK/scripts/lib/params.sh" || fail "--force did not rewrite params"
[ "$(value "$WORK/scripts/lib/secrets.sh" POSTGRES_PASSWORD)" != "$password" ] \
  || fail "--force did not generate a new password"
grep -q 'dining: 900' "$WORK/config/budget.yaml" || fail "--force overwrote the budget"
grep -q '# kept' "$WORK/backend/card-agents.ec2.yaml" || fail "--force overwrote a registry"

echo "test_init_env: all checks passed"
