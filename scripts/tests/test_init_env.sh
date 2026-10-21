#!/usr/bin/env bash
# Verifies init-env.sh: creates backend/.env and an empty registry; with backend/.env already
# there it still creates a missing registry and leaves the env file alone, so a clone set up before
# the registry existed gets one without losing its keys; --force alone rewrites backend/.env.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$WORK/scripts" "$WORK/backend"
cp "$SCRIPTS_DIR/common.sh" "$SCRIPTS_DIR/init-env.sh" "$WORK/scripts/"
printf 'LLM_MODEL=\nGOOGLE_CLIENT_ID=\n' > "$WORK/backend/.env.example"
init() { bash "$WORK/scripts/init-env.sh" "$@"; }

init >/dev/null
[ -f "$WORK/backend/.env" ] || fail "backend/.env not created"
[ "$(cat "$WORK/backend/card-agents.yaml")" = "agents: []" ] || fail "empty registry not created"
[ "$(stat -c %a "$WORK/backend/card-agents.yaml")" = "600" ] || fail "registry is not mode 600"

printf 'GOOGLE_CLIENT_ID=kept\n' > "$WORK/backend/.env"
rm "$WORK/backend/card-agents.yaml"
init >/dev/null || fail "refused to create the registry beside an existing backend/.env"
[ -f "$WORK/backend/card-agents.yaml" ] || fail "registry not created beside an existing .env"
grep -q 'GOOGLE_CLIENT_ID=kept' "$WORK/backend/.env" || fail "backend/.env was overwritten"

init --force >/dev/null
grep -q 'GOOGLE_CLIENT_ID=$' "$WORK/backend/.env" || fail "--force did not rewrite backend/.env"

echo "test_init_env: all checks passed"
