#!/usr/bin/env bash
# Verifies init-env.sh --sync-token: it copies the agent's APP_A2A_TOKEN over the existing
# AMEX_AGENT_TOKEN line, keeps every other line, and fails when backend/.env has no such line.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/scripts" "$WORK/backend" "$WORK/amex"
cp "$SCRIPTS_DIR/common.sh" "$SCRIPTS_DIR/init-env.sh" "$WORK/scripts/"
printf 'APP_A2A_TOKEN=agent_token-1\n' > "$WORK/amex/.env"

fail() { echo "FAIL: $*" >&2; exit 1; }
sync_token() {
  env -u AMEX_AGENT_DIR -u AMEX_AGENT_TOKEN bash "$WORK/scripts/init-env.sh" --sync-token
}

printf 'LLM_MODEL=openai:gpt-5-mini\nAMEX_AGENT_DIR=%s\nAMEX_STATEMENTS_DIR=%s/statements\n' \
  "$WORK/amex" "$WORK/amex" > "$WORK/backend/.env"
if sync_token >/dev/null 2>"$WORK/err"; then fail "succeeded without an AMEX_AGENT_TOKEN line"; fi
grep -q 'no AMEX_AGENT_TOKEN= line' "$WORK/err" || fail "missing line not named"

printf 'AMEX_AGENT_TOKEN=stale\n' >> "$WORK/backend/.env"
sync_token >/dev/null
grep -qx 'AMEX_AGENT_TOKEN=agent_token-1' "$WORK/backend/.env" || fail "token not copied"
grep -qx 'LLM_MODEL=openai:gpt-5-mini' "$WORK/backend/.env" || fail "another line was lost"

echo "test_sync_token: all checks passed"
