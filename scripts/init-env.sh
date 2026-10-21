#!/usr/bin/env bash
#
# Create backend/.env from backend/.env.example and an empty card-agent registry beside it. An
# existing backend/.env is kept unless --force; an existing registry is always kept, and a missing
# one is created even when backend/.env is already there.
#
#   ./scripts/init-env.sh             # create backend/.env and backend/card-agents.yaml
#   ./scripts/init-env.sh --force     # overwrite an existing backend/.env
#
# Then set GOOGLE_CLIENT_ID and the API key of LLM_MODEL's provider in backend/.env (docs/sign-in.md
# walks through the Google Cloud side) and run ./scripts/start.sh. Card agents are connected later
# with ./scripts/add-card-agent.sh; the manager runs without any.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force)   FORCE=1 ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Usage: ./scripts/init-env.sh [--force]" >&2; exit 2 ;;
  esac
  shift
done

# backend/.env holds provider keys and the registry holds card-agent secrets, so only the owner
# may read them. umask covers a new file; chmod covers one rewritten in place.
umask 077
if [ -f "$ENV_FILE" ] && [ "$FORCE" -eq 0 ]; then
  echo "backend/.env already exists; left as it is (--force overwrites it)."
else
  cp "$BACKEND/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Created backend/.env."
fi
if [ -f "$REGISTRY_FILE" ]; then
  echo "$REGISTRY_FILE already exists; left as it is."
else
  printf 'agents: []\n' > "$REGISTRY_FILE"
  echo "Created $REGISTRY_FILE with no card agents."
fi
echo "Next: set GOOGLE_CLIENT_ID and the API key for LLM_MODEL in backend/.env, then" \
     "./scripts/start.sh. Connect a card agent later with ./scripts/add-card-agent.sh."
