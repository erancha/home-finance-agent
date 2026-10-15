#!/usr/bin/env bash
# Verifies load_env from scripts/common.sh: backend/.env supplies defaults, a variable already
# exported by the caller wins even over a blank line, one pair of surrounding quotes is stripped,
# a blank card-agent path aborts by name, and a malformed line aborts.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/scripts" "$WORK/backend"
cp "$SCRIPTS_DIR/common.sh" "$WORK/scripts/common.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }

cat > "$WORK/backend/.env" <<'ENV'
# a comment

PLAIN=plain
DOUBLE="two words"
SINGLE='single quoted'
KEPT=from-env-file
BLANKED=
AMEX_AGENT_DIR=/agent
AMEX_STATEMENTS_DIR=/agent/statements
ENV

# Runs in a subshell so the sourced helpers and exported values do not leak between cases.
run_load_env() {
  # The developer's own exported AMEX_* values must not reach the case under test.
  (unset AMEX_AGENT_DIR AMEX_STATEMENTS_DIR AMEX_AGENT_TOKEN AMEX_AGENT_URL
   export KEPT=from-caller BLANKED=from-caller; . "$WORK/scripts/common.sh"; load_env; "$@")
}

[[ "$(run_load_env bash -c 'echo "$KEPT"')" == "from-caller" ]] || fail "caller value overwritten"
[[ "$(run_load_env bash -c 'echo "$BLANKED"')" == "from-caller" ]] || fail "blank line cleared it"
[[ "$(run_load_env bash -c 'echo "$PLAIN"')" == "plain" ]] || fail "plain value not loaded"
[[ "$(run_load_env bash -c 'echo "$DOUBLE"')" == "two words" ]] || fail "double quotes kept"
[[ "$(run_load_env bash -c 'echo "$SINGLE"')" == "single quoted" ]] || fail "single quotes kept"
[[ "$(run_load_env bash -c 'echo "$AMEX_STATEMENTS_DIR"')" == "/agent/statements" ]] \
  || fail "statements folder not loaded"

printf 'AMEX_AGENT_DIR=/agent\nAMEX_STATEMENTS_DIR=\n' > "$WORK/backend/.env"
if run_load_env true 2>"$WORK/err"; then fail "blank AMEX_STATEMENTS_DIR accepted"; fi
grep -q 'AMEX_STATEMENTS_DIR is blank' "$WORK/err" || fail "blank folder not named"

for bad in "export FOO=1" "BAD LINE"; do
  printf 'OK=1\n%s\n' "$bad" > "$WORK/backend/.env"
  if run_load_env true 2>"$WORK/err"; then fail "accepted malformed line: $bad"; fi
  grep -q '\.env:2:' "$WORK/err" || fail "no line number reported for: $bad"
done

echo "test_load_env: all checks passed"
