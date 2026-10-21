#!/usr/bin/env bash
# Verifies add-card-agent.sh: writes an entry the manager's loader reads, replaces an entry by
# name while keeping the others, starts from the empty registry init-env.sh writes, creates the
# file owner-readable only, and refuses a blank option, a value that is not a plain scalar, and a
# file it did not write.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FILE="$WORK/card-agents.yaml"
fail() { echo "FAIL: $*" >&2; exit 1; }
add() { bash "$SCRIPTS_DIR/add-card-agent.sh" --file "$FILE" "$@"; }
HEADER='# Card agents this home finance agent reviews with; written by scripts/add-card-agent.sh.'

printf 'agents: []\n' > "$FILE"
add --name amex --url http://host.docker.internal:8020 --browser-url http://localhost:8020 \
  --secret s3cret-1 >/dev/null
[ "$(stat -c %a "$FILE")" = "600" ] || fail "registry is not mode 600"
add --name visa --url http://visa:8030 --browser-url http://localhost:8030 --secret s3cret-2 \
  >/dev/null
add --name amex --url http://host.docker.internal:8020 --browser-url http://localhost:8020 \
  --secret s3cret-3 >/dev/null
expected="$HEADER
agents:
  - name: visa
    url: http://visa:8030
    browser_url: http://localhost:8030
    shared_secret: s3cret-2
  - name: amex
    url: http://host.docker.internal:8020
    browser_url: http://localhost:8020
    shared_secret: s3cret-3"
[ "$(cat "$FILE")" = "$expected" ] || fail "unexpected registry: $(cat "$FILE")"

rm "$FILE"
add --name amex --url http://x:1 --browser-url http://y:2 --secret s >/dev/null
grep -q '^  - name: amex$' "$FILE" || fail "registry not created when absent"

if add --name "" --url http://x:1 --browser-url http://y:2 --secret s >/dev/null 2>"$WORK/err"; then
  fail "accepted a blank name"
fi
grep -q -- '--name' "$WORK/err" || fail "blank name not named"
if add --name amex --url http://x:1 --browser-url http://y:2 --secret 'a b' >/dev/null 2>&1; then
  fail "accepted a secret with a space"
fi
if add --name amex --url localhost:8020 --browser-url http://y:2 --secret s >/dev/null 2>&1; then
  fail "accepted a URL without a scheme"
fi

printf 'agents: [\n' > "$FILE"
if add --name amex --url http://x:1 --browser-url http://y:2 --secret s >/dev/null 2>"$WORK/err"
then fail "rewrote a file it did not write"; fi

# Without --file the script writes the registry start.sh mounts: CARD_AGENTS_FILE from backend/.env
# when set, the default beside it otherwise.
mkdir -p "$WORK/scripts" "$WORK/backend"
cp "$SCRIPTS_DIR/common.sh" "$SCRIPTS_DIR/add-card-agent.sh" "$WORK/scripts/"
bash "$WORK/scripts/add-card-agent.sh" --name amex --url http://x:1 --browser-url http://y:2 \
  --secret s >/dev/null
[ -f "$WORK/backend/card-agents.yaml" ] || fail "default registry not written beside backend/.env"
printf 'CARD_AGENTS_FILE=%s\n' "$WORK/elsewhere.yaml" > "$WORK/backend/.env"
bash "$WORK/scripts/add-card-agent.sh" --name amex --url http://x:1 --browser-url http://y:2 \
  --secret s >/dev/null
[ -f "$WORK/elsewhere.yaml" ] || fail "CARD_AGENTS_FILE from backend/.env not honoured"

echo "test_add_card_agent: all checks passed"
