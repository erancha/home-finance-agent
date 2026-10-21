#!/usr/bin/env bash
# Verifies load_env and require_registry from scripts/common.sh: backend/.env supplies defaults, a
# variable already exported by the caller wins even over a blank line, one pair of surrounding
# quotes is stripped, a malformed line aborts, the registry path and the host uid and gid are
# exported with their defaults, and a launch without the registry file is refused naming
# init-env.sh.
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
ENV

# Runs in a subshell so the sourced helpers and exported values do not leak between cases.
run_load_env() {
  (export KEPT=from-caller BLANKED=from-caller; . "$WORK/scripts/common.sh"; load_env; "$@")
}

[[ "$(run_load_env bash -c 'echo "$KEPT"')" == "from-caller" ]] || fail "caller value overwritten"
[[ "$(run_load_env bash -c 'echo "$BLANKED"')" == "from-caller" ]] || fail "blank line cleared it"
[[ "$(run_load_env bash -c 'echo "$PLAIN"')" == "plain" ]] || fail "plain value not loaded"
[[ "$(run_load_env bash -c 'echo "$DOUBLE"')" == "two words" ]] || fail "double quotes kept"
[[ "$(run_load_env bash -c 'echo "$SINGLE"')" == "single quoted" ]] || fail "single quotes kept"
[[ "$(run_load_env bash -c 'echo "$CARD_AGENTS_FILE"')" == "$WORK/backend/card-agents.yaml" ]] \
  || fail "registry path default not exported"
[[ "$(CARD_AGENTS_FILE=/elsewhere.yaml run_load_env bash -c 'echo "$CARD_AGENTS_FILE"')" \
    == "/elsewhere.yaml" ]] || fail "exported registry path overwritten"
[[ "$(run_load_env bash -c 'echo "$HOST_UID:$HOST_GID"')" == "$(id -u):$(id -g)" ]] \
  || fail "host uid and gid not exported"
[[ "$(HOST_UID=42 run_load_env bash -c 'echo "$HOST_UID"')" == "42" ]] \
  || fail "exported host uid overwritten"

if run_load_env require_registry 2>"$WORK/err"; then fail "accepted a missing registry"; fi
grep -q 'init-env.sh' "$WORK/err" || fail "missing registry does not name init-env.sh"
printf 'agents: []\n' > "$WORK/backend/card-agents.yaml"
run_load_env require_registry || fail "refused an existing registry"

for bad in "export FOO=1" "BAD LINE"; do
  printf 'OK=1\n%s\n' "$bad" > "$WORK/backend/.env"
  if run_load_env true 2>"$WORK/err"; then fail "accepted malformed line: $bad"; fi
  grep -q '\.env:2:' "$WORK/err" || fail "no line number reported for: $bad"
done

echo "test_load_env: all checks passed"
