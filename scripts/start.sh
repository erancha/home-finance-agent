#!/usr/bin/env bash
#
# Run the home finance agent: database, migrations and manager. Docker is the default; --host runs
# the manager as a local process for fast restarts and debugger attach. Either way the page is
# http://localhost:8010 (the React app at /); the manager listens on every interface, so other
# devices on the network use this machine's address.
#
#   ./scripts/start.sh            # db, migrations and manager via docker compose
#   ./scripts/start.sh --host     # db in Docker; manager (uvicorn) on the host
#
# Docker mode builds the image, applies migrations in a one-shot service and returns once the
# manager is healthy. Host mode provisions backend/.venv, starts PostgreSQL via compose, applies
# migrations, rebuilds the frontend when its sources changed, and runs uvicorn; Ctrl-C stops it.
#
# Card agents come from backend/card-agents.yaml (./scripts/add-card-agent.sh), read at startup, so
# rerun this script after connecting one. The manager calls the URL an agent's card advertises,
# which must be reachable from where the manager runs: in Docker an agent on this machine is
# http://host.docker.internal:<port>, in --host mode http://localhost:<port>.
#
# Requires backend/.env and the registry (./scripts/init-env.sh). Stop or inspect the Docker
# stack with ./scripts/docker-helper.sh (--stop / --logs / --ps).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

HOST=0
for arg in "$@"; do
  case "$arg" in
    --host)    HOST=1 ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Usage: ./scripts/start.sh [--host]" >&2; exit 2 ;;
  esac
done

require_env
load_env
require_registry
require_docker
MANAGER=http://localhost:8010

if [ "$HOST" -eq 0 ]; then
  echo "Deploying db + migrations + manager to Docker..."
  compose up -d --build
  wait_for_url "$MANAGER/health" \
    || { echo "manager did not become healthy; see ./scripts/docker-helper.sh --logs" >&2
         exit 1; }
  echo "Open $MANAGER in your browser and sign in with Google."
  echo "  health: $MANAGER/health   ready: $MANAGER/ready"
  echo "  stop the stack or tail logs:  ./scripts/docker-helper.sh --stop | --logs"
  exit 0
fi

command -v npm >/dev/null 2>&1 || { echo "npm not found; install Node.js 22 and retry." >&2; exit 1; }
ensure_venv

compose up -d db
printf 'Waiting for PostgreSQL'
for attempt in $(seq 30); do
  if compose exec -T db pg_isready -U hfm -d hfm >/dev/null 2>&1; then
    echo " ready."; break
  fi
  [ "$attempt" -lt 30 ] || { echo " not ready after 30 s." >&2; exit 1; }
  printf '.'; sleep 1
done
( cd "$BACKEND" && "$VENV/bin/alembic" upgrade head )

# dist doubles as the freshness marker: rebuild only when something under frontend/ outside
# node_modules and dist itself is newer than it. Inputs are everything-but-outputs rather than an
# enumerated list, so a new config or asset can only over-trigger a redundant build, never go stale.
if [ ! -d "$FRONTEND/dist" ] || [ -n "$(find "$FRONTEND" \
      \( -path "$FRONTEND/node_modules" -o -path "$FRONTEND/dist" \) -prune \
      -o -newer "$FRONTEND/dist" -print -quit)" ]; then
  echo "Building frontend..."
  # Dependencies reinstall only when a manifest changed since dist was produced (or on first build).
  ( cd "$FRONTEND" \
    && { { [ -d node_modules ] && ! [ package.json -nt dist ] && ! [ package-lock.json -nt dist ]; } \
         || npm ci --no-audit --no-fund; } \
    && npm run build )
else
  echo "Frontend dist is up to date; skipping build."
fi
export HFM_FRONTEND_DIST="$FRONTEND/dist" LANGGRAPH_STRICT_MSGPACK=true

# uvicorn runs as a background child so one Ctrl-C (delivered to the whole process group) stops
# the launch; waiting after the kill lets its graceful shutdown finish before the prompt returns.
pids=()
cleanup() {
  [ ${#pids[@]} -gt 0 ] || return 0
  kill "${pids[@]}" 2>/dev/null || true
  wait "${pids[@]}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting the manager; open $MANAGER in your browser and sign in with Google." \
     "Ctrl-C stops it."
# Run from the repo root: backend/card-agents.yaml and config/budget.yaml resolve against it.
( cd "$ROOT" && exec "$VENV/bin/uvicorn" hfm.platform.app:create_app --factory \
    --host 0.0.0.0 --port 8010 --timeout-graceful-shutdown 5 ) &
pids+=($!)

wait "${pids[@]}"
