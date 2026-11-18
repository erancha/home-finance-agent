#!/usr/bin/env bash
#
# Run the test suites of the home finance agent.
#
#   ./scripts/test.sh                      # backend + frontend (default)
#   ./scripts/test.sh all                  # backend + frontend (explicit)
#   ./scripts/test.sh backend              # the agent in backend/ and the scripts  (alias: be)
#   ./scripts/test.sh frontend             # the page in frontend/  (alias: fe)
#   ./scripts/test.sh e2e [--amex-dir D]   # full stack in Docker, a review through both agents;
#                                          # D is the amex-agent checkout, default
#                                          # ../../java/amex-agent beside this repo
#
# Targets combine, so several may be given.
#
# The backend target runs: the scripts' syntax check (bash -n) and their shell tests under
# scripts/tests/, lint (ruff), typecheck (mypy), import-linter layer contracts, and pytest, whose
# integration tests start an ephemeral Postgres and Redis via Testcontainers, so Docker must be
# running. The frontend target runs lint (oxlint), component tests (vitest), then the typecheck
# (tsc) and production build (vite) that npm run build chains.
#
# The e2e target is opt-in and never part of the default, and the one place both repos meet: it
# builds amex-agent from its checkout and brings the stack up as its own compose project (hfm-e2e,
# with its own database volume) with both agents on their e2e stand-ins for a language model
# (canned report, keyword classifier), on a test issuer whose key pair this run generates instead
# of Google, connected through a generated registry and callers file, and the agent on an empty
# temporary statements folder. It runs scripts/tests/e2e/run_review.py against it, which signs in
# with that key, loads amex-agent's test statement into that folder and reviews the month, and
# removes the project, its volume and the folders on every exit. It runs ./scripts/init-env.sh
# first; the settings files' model and sign-in values are overridden.
#
# The review relies on a database that has never learnt the test statement's club, so it refuses
# to start while an hfm-e2e stack is up. The development stack publishes the same ports, so it
# must be stopped first.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
  echo "Usage: ./scripts/test.sh [all|backend|frontend|e2e [--amex-dir D]] ..." \
       "(aliases: be, fe)" >&2
  exit 2
}

RUN_BACKEND=false
RUN_FRONTEND=false
RUN_E2E=false
AMEX_DIR_FLAG=""
selected=false

while [ $# -gt 0 ]; do
  arg="$1"
  shift
  case "$(printf '%s' "$arg" | tr '[:upper:]' '[:lower:]')" in
    -h|--help)   print_help; exit 0 ;;
    all)         RUN_BACKEND=true; RUN_FRONTEND=true ;;
    be|backend)  RUN_BACKEND=true ;;
    fe|frontend) RUN_FRONTEND=true ;;
    e2e)         RUN_E2E=true ;;
    --amex-dir)  AMEX_DIR_FLAG="${1:?--amex-dir needs a path}"; shift; continue ;;
    *) usage ;;
  esac
  selected=true
done
if [ -n "$AMEX_DIR_FLAG" ] && [ "$RUN_E2E" = false ]; then
  echo "--amex-dir applies to the e2e target only" >&2
  exit 2
fi

if [ "$selected" = false ]; then
  RUN_BACKEND=true
  RUN_FRONTEND=true
fi

run_backend() {
  echo "==> Backend"
  echo "--> scripts (bash -n, shell tests)"
  for script in "$ROOT"/scripts/*.sh "$ROOT"/scripts/lib/*.sh "$ROOT"/scripts/tools/*.sh \
      "$ROOT/.githooks/pre-commit"; do
    bash -n "$script"
  done
  for check in "$ROOT"/scripts/tests/test_*.sh; do bash "$check"; done
  ensure_backend_venv
  echo "--> lint (ruff)"
  ( cd "$BACKEND" && "$BACKEND_VENV/bin/ruff" check src tests )
  echo "--> typecheck (mypy)"
  ( cd "$BACKEND" && "$BACKEND_VENV/bin/mypy" )
  echo "--> import-linter (layer contracts)"
  ( cd "$BACKEND" && "$BACKEND_VENV/bin/lint-imports" )
  echo "--> pytest"
  ( cd "$BACKEND" && "$BACKEND_VENV/bin/pytest" )
}

run_frontend() {
  echo "==> Frontend"
  command -v npm >/dev/null 2>&1 \
    || { echo "npm not found; install Node.js 22 and retry." >&2; exit 1; }
  # npm ci installs the lockfile verbatim; npm install may re-resolve and mutate it. npm writes
  # node_modules/.package-lock.json on install, so a lockfile newer than it was edited since.
  if [ ! "$FRONTEND/node_modules/.package-lock.json" -nt "$FRONTEND/package-lock.json" ]; then
    ( cd "$FRONTEND" && npm ci --no-audit --no-fund )
  fi
  echo "--> lint (oxlint)"
  ( cd "$FRONTEND" && npm run --silent lint )
  echo "--> component tests (vitest)"
  ( cd "$FRONTEND" && npm run --silent test )
  echo "--> typecheck and build (tsc -b, vite build)"
  ( cd "$FRONTEND" && npm run --silent build )
}

E2E_COMPOSE_FILE="$ROOT/docker-compose.e2e.yml"
e2e_compose() {
  local -a COMPOSE_FILES=("${COMPOSE_FILES[@]}" "$E2E_COMPOSE_FILE")
  compose -p hfm-e2e "$@"
}

e2e_teardown() {
  e2e_compose down -v --remove-orphans
  rm -rf "$E2E_STATEMENTS_DIR" "$E2E_AUTH_DIR" "$E2E_PRIVATE_DIR"
}

run_e2e() {
  echo "==> E2E (docker compose project hfm-e2e)"
  "$SCRIPT_DIR/init-env.sh"
  load_settings
  require_docker
  ensure_backend_venv
  # amex-agent is built from its own checkout and runs as this user, who owns the statements
  # folder it writes uploads into and the auth folder it reads.
  export AMEX_AGENT_DIR HOST_UID HOST_GID
  HOST_UID="$(id -u)"
  HOST_GID="$(id -g)"
  AMEX_AGENT_DIR="$(cd "$ROOT" && cd "${AMEX_DIR_FLAG:-../../java/amex-agent}" 2>/dev/null \
                    && pwd)" \
    || { echo "amex-agent checkout not found; pass --amex-dir <path>" >&2; exit 1; }
  # Compose needs the folders' paths for every e2e call, the checks below included.
  export E2E_STATEMENTS_DIR E2E_AUTH_DIR
  E2E_STATEMENTS_DIR="$(mktemp -d)"
  # amex-agent reads the public key and the callers file from the first folder; the private key
  # stays in the second, which no container mounts.
  E2E_AUTH_DIR="$(mktemp -d)"
  E2E_PRIVATE_DIR="$(mktemp -d)"
  trap 'rm -rf "$E2E_STATEMENTS_DIR" "$E2E_AUTH_DIR" "$E2E_PRIVATE_DIR"' EXIT
  "$BACKEND_VENV/bin/python" "$ROOT/scripts/tests/e2e/make_auth.py" "$E2E_AUTH_DIR" \
    "$E2E_PRIVATE_DIR"
  # This check runs before the registry is swapped, so compose reads the development stack's.
  if [ -n "$(compose ps --status running -q)" ]; then
    echo "The development stack is up on the same ports; stop it first:" \
      "./scripts/docker-helper.sh --stop" >&2
    exit 1
  fi
  # The manager's card-agents secret holds the generated registry in place of the development one.
  REGISTRY_FILE="$E2E_AUTH_DIR/card-agents.yaml"
  # A running e2e stack has already learnt the club, so this run would fail misleadingly.
  if [ -n "$(e2e_compose ps -q)" ]; then
    echo "The hfm-e2e stack is already up; remove it first:" \
      "docker compose -p hfm-e2e down -v" >&2
    exit 1
  fi
  # The e2e publishes amex-agent on 8020 too; a separately deployed agent there would take the port.
  if curl -fs --max-time 2 -o /dev/null http://localhost:8020/actuator/health; then
    echo "An agent already answers on http://localhost:8020; stop it first (amex-agent's" \
      "./scripts/docker-helper.sh --stop)" >&2
    exit 1
  fi
  # This run owns the project from here on, so every exit path, Ctrl-C included, removes it.
  trap e2e_teardown EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  if ! e2e_compose up -d --build --wait; then
    e2e_compose logs --tail=100
    exit 1
  fi
  local status=0
  local statement
  statement="$AMEX_AGENT_DIR/src/test/resources/statements/2026-10.pdf"
  "$BACKEND_VENV/bin/python" "$ROOT/scripts/tests/e2e/run_review.py" \
    "http://localhost:$EDGE_HOST_PORT" "$statement" "$E2E_PRIVATE_DIR/auth-private.pem" \
    || status=$?
  if [ "$status" -ne 0 ]; then
    echo "--> last log lines of the failed run"
    e2e_compose logs --tail=100 manager amex-agent
  fi
  trap - EXIT INT TERM
  e2e_teardown
  return "$status"
}

if [ "$RUN_BACKEND" = true ]; then run_backend; fi
if [ "$RUN_FRONTEND" = true ]; then run_frontend; fi
if [ "$RUN_E2E" = true ]; then run_e2e; fi

echo "All requested tests passed."
