#!/usr/bin/env bash
#
# Create backend/.env from backend/.env.example and share one A2A bearer token with the amex-agent
# repo: its APP_A2A_TOKEN is reused when its .env exists, otherwise a token is minted here and that
# repo's own init-env.sh creates its .env with it. Refuses to clobber backend/.env without --force.
#
#   ./scripts/init-env.sh                     # amex-agent where backend/.env.example says
#   ./scripts/init-env.sh --force             # overwrite an existing backend/.env
#   ./scripts/init-env.sh --amex-dir <path>   # amex-agent elsewhere: recorded as AMEX_AGENT_DIR,
#                                             # its statements/ folder as AMEX_STATEMENTS_DIR
#   ./scripts/init-env.sh --sync-token        # only copy the agent's current token into the
#                                             # existing backend/.env, keeping every other line
#
# Then set the API key of LLM_MODEL's provider in backend/.env; the app will not start without it.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

FORCE=0
SYNC=0
AMEX_DIR_FLAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --force)      FORCE=1 ;;
    --sync-token) SYNC=1 ;;
    --amex-dir)   AMEX_DIR_FLAG="${2:?--amex-dir needs a path}"; shift ;;
    -h|--help)    print_help; exit 0 ;;
    *) echo "Usage: ./scripts/init-env.sh [--force] [--amex-dir <path>] | --sync-token" >&2
       exit 2 ;;
  esac
  shift
done

# backend/.env holds the token and provider keys, so only the owner may read it. umask covers a
# new file; chmod covers one rewritten in place.
umask 077

# The sed replacements below rely on this alphabet (url-safe base64, never the '|' delimiter).
require_token_alphabet() {  # token source-file
  [[ "$1" =~ ^[A-Za-z0-9_-]+$ ]] \
    || { echo "APP_A2A_TOKEN in $2 holds characters outside [A-Za-z0-9_-]." >&2; exit 1; }
}

if [ "$SYNC" -eq 1 ]; then
  [ "$FORCE" -eq 0 ] && [ -z "$AMEX_DIR_FLAG" ] \
    || { echo "--sync-token takes no other option; AMEX_AGENT_DIR comes from backend/.env." >&2
         exit 2; }
  require_env
  load_env
  AMEX_ENV="$(amex_env_file)"
  [ -f "$AMEX_ENV" ] \
    || { echo "$AMEX_ENV not found; run ./scripts/init-env.sh --force" >&2; exit 1; }
  TOKEN="$(amex_token)"
  [ -n "$TOKEN" ] || { echo "$AMEX_ENV has no APP_A2A_TOKEN value." >&2; exit 1; }
  require_token_alphabet "$TOKEN" "$AMEX_ENV"
  grep -q '^AMEX_AGENT_TOKEN=' "$ENV_FILE" \
    || { echo "$ENV_FILE has no AMEX_AGENT_TOKEN= line to set; add one or rerun with --force." >&2
         exit 1; }
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  sed -e "s|^AMEX_AGENT_TOKEN=.*|AMEX_AGENT_TOKEN=${TOKEN}|" "$ENV_FILE" > "$tmp"
  mv "$tmp" "$ENV_FILE"
  echo "Set AMEX_AGENT_TOKEN in backend/.env to APP_A2A_TOKEN from $AMEX_ENV."
  exit 0
fi

if [ -f "$ENV_FILE" ] && [ "$FORCE" -eq 0 ]; then
  echo "backend/.env already exists; pass --force to overwrite it." >&2
  exit 1
fi

example_value() { sed -n "s|^$1=||p" "$BACKEND/.env.example"; }  # key
if [ -n "$AMEX_DIR_FLAG" ]; then
  AMEX_AGENT_DIR="$(cd "$AMEX_DIR_FLAG" && pwd)"
  AMEX_STATEMENTS_DIR="$AMEX_AGENT_DIR/statements"
else
  AMEX_AGENT_DIR="$(example_value AMEX_AGENT_DIR)"
  AMEX_STATEMENTS_DIR="$(example_value AMEX_STATEMENTS_DIR)"
fi
require_agent_paths
AMEX_ENV="$(amex_env_file)"

if [ -f "$AMEX_ENV" ]; then
  TOKEN="$(amex_token)"
  [ -n "$TOKEN" ] || { echo "$AMEX_ENV has no APP_A2A_TOKEN value." >&2; exit 1; }
  echo "Reusing APP_A2A_TOKEN from $AMEX_ENV."
else
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  "$(abs_from_root "$AMEX_AGENT_DIR")/scripts/init-env.sh" --token "$TOKEN"
  echo "Created $AMEX_ENV with a freshly minted APP_A2A_TOKEN."
fi
require_token_alphabet "$TOKEN" "$AMEX_ENV"

sed -e "s|^AMEX_AGENT_TOKEN=.*|AMEX_AGENT_TOKEN=${TOKEN}|" \
    -e "s|^AMEX_AGENT_DIR=.*|AMEX_AGENT_DIR=${AMEX_AGENT_DIR}|" \
    -e "s|^AMEX_STATEMENTS_DIR=.*|AMEX_STATEMENTS_DIR=${AMEX_STATEMENTS_DIR}|" \
    "$BACKEND/.env.example" > "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "Created backend/.env with AMEX_AGENT_TOKEN equal to amex-agent's APP_A2A_TOKEN."
echo "amex-agent repo: $(abs_from_root "$AMEX_AGENT_DIR"); statements folder: $AMEX_STATEMENTS_DIR."
echo "Set the API key for LLM_MODEL in backend/.env (and the model and key in amex-agent's .env)."
