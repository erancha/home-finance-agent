#!/usr/bin/env bash
#
# Run the home finance agent together with amex-agent. Docker is the default; --host runs both as
# local processes for fast restarts and debugger attach. Either way the home finance agent answers
# on http://localhost:8010 (the React app at /) and amex-agent on http://localhost:8020; the home
# finance agent listens on every interface, so other devices on the network use this machine's
# address.
#
#   ./scripts/start.sh            # db, migrations, amex-agent and manager via docker compose
#   ./scripts/start.sh --host     # db in Docker; agent (mvn) and manager (uvicorn) on the host
#
# Docker mode builds both images, applies migrations in a one-shot service and returns once both
# agents are healthy. Host mode provisions backend/.venv, starts PostgreSQL via compose, applies
# migrations, launches the agent through its own scripts/start.sh --host (its .env governs it,
# except the statements folder, which is AMEX_STATEMENTS_DIR in both modes), rebuilds the frontend
# when its sources changed, and runs uvicorn; Ctrl-C stops both.
#
# Refuses to start when AMEX_AGENT_TOKEN in backend/.env differs from the agent's APP_A2A_TOKEN
# (./scripts/init-env.sh --sync-token realigns it).
#
# Requires backend/.env (./scripts/init-env.sh). Stop or inspect the Docker stack with
# ./scripts/docker-helper.sh (--stop / --logs / --ps).
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
require_matching_token
require_docker
MANAGER=http://localhost:8010
AGENT_HEALTH="$AGENT_BASE/actuator/health"

if [ "$HOST" -eq 0 ]; then
  echo "Deploying db + migrations + amex-agent + manager to Docker..."
  compose up -d --build
  wait_for_url "$AGENT_HEALTH" \
    || { echo "amex-agent did not become healthy; see ./scripts/docker-helper.sh --logs" >&2; exit 1; }
  wait_for_url "$MANAGER/health" \
    || { echo "manager did not become healthy; see ./scripts/docker-helper.sh --logs" >&2; exit 1; }
  echo "  manager    -> $MANAGER   (React app at /, ready: /ready)"
  echo "  amex-agent -> $AGENT_BASE/.well-known/agent-card.json"
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

# Both run as background children waited on together, so one Ctrl-C (delivered to the whole
# process group) stops the launch, and either one exiting tears down the other. Waiting after the
# kill lets uvicorn's graceful shutdown and the agent's stop finish before the prompt returns.
pids=()
cleanup() {
  [ ${#pids[@]} -gt 0 ] || return 0
  kill "${pids[@]}" 2>/dev/null || true
  wait "${pids[@]}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# The agent's load_env keeps an exported value over its own .env, so this folder wins there.
APP_STATEMENTS_DIR="$(abs_from_root "$AMEX_STATEMENTS_DIR")"
export APP_STATEMENTS_DIR

"$(abs_from_root "$AMEX_AGENT_DIR")/scripts/start.sh" --host &
pids+=($!)
for _ in $(seq 120); do
  curl -fs --max-time 2 -o /dev/null "$AGENT_HEALTH" && break
  kill -0 "${pids[0]}" 2>/dev/null || { echo "amex-agent exited during startup." >&2; exit 1; }
  sleep 1
done
curl -fs --max-time 2 -o /dev/null "$AGENT_HEALTH" \
  || { echo "amex-agent did not become healthy within 120 s." >&2; exit 1; }

echo "Starting manager -> $MANAGER   (React app at /, health: /health, ready: /ready)"
# Run from the repo root: config/agents.yaml and config/budget.yaml resolve against it.
( cd "$ROOT" && exec "$VENV/bin/uvicorn" hfm.platform.app:create_app --factory --host 0.0.0.0 --port 8010 \
    --timeout-graceful-shutdown 5 ) &
pids+=($!)

wait -n "${pids[@]}"
