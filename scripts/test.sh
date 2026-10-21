#!/usr/bin/env bash
#
# Run the test suites of the home finance agent.
#
#   ./scripts/test.sh                        # backend + frontend (default)
#   ./scripts/test.sh all                    # backend + frontend (explicit)
#   ./scripts/test.sh backend                # backend only  (alias: be)
#   ./scripts/test.sh frontend               # frontend, full (alias: fe)
#   ./scripts/test.sh frontend=unit          # frontend fast path only (alias: fe=u)
#   ./scripts/test.sh backend frontend=unit  # combine targets: full backend + fast frontend
#   ./scripts/test.sh e2e [--amex-dir D]     # full stack in Docker, a review through both agents;
#                                            # D is the amex-agent checkout, default
#                                            # ../../java/amex-agent beside this repo
#
# Each argument is a target with an optional =mode. Targets combine, so several may be given.
#
# Backend: the scripts' shell checks, lint (ruff), typecheck (mypy), import-linter layer
# contracts, and pytest. Integration tests start an ephemeral PostgreSQL via Testcontainers, so
# Docker must be running. Frontend: typecheck (tsc), lint (oxlint), component tests (vitest), and a
# production build (vite). The =unit mode keeps the typecheck and tests but skips oxlint and the
# build.
#
# The e2e target is opt-in and never part of the default, and the one place both repos meet: it
# builds amex-agent from its checkout and brings the stack up as its own compose project (hfm-e2e,
# with its own database volume) with both agents on their e2e stand-ins for a language model
# (canned report, keyword classifier), on a test issuer whose key pair this run generates instead
# of Google, connected through a generated registry and callers file, and the agent on an empty
# temporary statements folder. It runs scripts/tests/e2e/run_review.py against it, which signs in
# with that key, loads amex-agent's test statement into that folder and reviews the month, and
# removes the project, its volume and the folders on every exit. backend/.env must exist
# (./scripts/init-env.sh); its values are overridden.
#
# The review relies on a database that has never learnt the test statement's club, so it refuses
# to start while an hfm-e2e stack is up. The development stack publishes the same ports, so it
# must be stopped first.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
  echo "Usage: ./scripts/test.sh [all|backend|frontend[=unit]|e2e [--amex-dir D]] ..." \
       "(aliases: be | fe | u)" >&2
  exit 2
}

RUN_BACKEND=false
RUN_FRONTEND=false
RUN_E2E=false
FRONTEND_MODE="full"
AMEX_DIR_FLAG=""
selected=false

while [ $# -gt 0 ]; do
  arg="$1"
  shift
  if [ "$arg" = "--amex-dir" ]; then
    AMEX_DIR_FLAG="${1:?--amex-dir needs a path}"
    shift
    continue
  fi
  raw="$(printf '%s' "$arg" | tr '[:upper:]' '[:lower:]')"
  name="${raw%%=*}"
  mode="${raw#*=}"
  [ "$mode" = "$raw" ] && mode=""   # no '=' present, so no mode attached

  case "$name" in
    -h|--help)  print_help; exit 0 ;;
    all)        RUN_BACKEND=true; RUN_FRONTEND=true; fe_arg=true ;;
    be*|back*)  RUN_BACKEND=true; fe_arg=false ;;
    fe*|front*) RUN_FRONTEND=true; fe_arg=true ;;
    e2e)        RUN_E2E=true; fe_arg=false ;;
    *) usage ;;
  esac
  selected=true

  if [ -n "$mode" ]; then
    [ "$fe_arg" = true ] || { echo "=$mode applies to the frontend only (got: $arg)" >&2; exit 2; }
    case "$mode" in
      u*|unit) FRONTEND_MODE="unit" ;;
      full)    FRONTEND_MODE="full" ;;
      *) usage ;;
    esac
  fi
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
  echo "--> scripts (shell checks)"
  for check in "$ROOT"/scripts/tests/test_*.sh; do bash "$check"; done
  ensure_venv
  echo "--> lint (ruff)"
  ( cd "$BACKEND" && "$VENV/bin/ruff" check src tests )
  echo "--> typecheck (mypy)"
  ( cd "$BACKEND" && "$VENV/bin/mypy" )
  echo "--> import-linter (layer contracts)"
  ( cd "$BACKEND" && "$VENV/bin/lint-imports" )
  echo "--> pytest (unit + integration + API)"
  ( cd "$BACKEND" && "$VENV/bin/pytest" )
}

run_frontend() {
  echo "==> Frontend"
  command -v npm >/dev/null 2>&1 \
    || { echo "npm not found; install Node.js 22 and retry." >&2; exit 1; }
  # npm ci installs the lockfile verbatim; npm install may re-resolve and mutate it.
  [ -d "$FRONTEND/node_modules" ] || ( cd "$FRONTEND" && npm ci --no-audit --no-fund )
  echo "--> typecheck (tsc -b)"
  ( cd "$FRONTEND" && npx tsc -b )
  if [ "$FRONTEND_MODE" != unit ]; then
    echo "--> lint (oxlint)"
    ( cd "$FRONTEND" && npm run --silent lint )
  fi
  echo "--> component tests (vitest)"
  ( cd "$FRONTEND" && npm run --silent test )
  if [ "$FRONTEND_MODE" != unit ]; then
    echo "--> build (vite)"
    ( cd "$FRONTEND" && npm run --silent build )
  fi
}

e2e_compose() {
  (cd "$ROOT" && docker compose -p hfm-e2e -f "$COMPOSE_FILE" -f "$E2E_COMPOSE_FILE" "$@")
}

e2e_teardown() {
  e2e_compose down -v --remove-orphans
  rm -rf "$E2E_STATEMENTS_DIR" "$E2E_AUTH_DIR" "$E2E_PRIVATE_DIR"
}

run_e2e() {
  echo "==> E2E (docker compose project hfm-e2e)"
  require_env
  load_env
  require_docker
  ensure_venv
  # The agent is built from its own checkout and, like the manager, runs as the host user
  # (HOST_UID/HOST_GID from load_env), who owns the statements folder it writes uploads into.
  export AMEX_AGENT_DIR
  AMEX_AGENT_DIR="$(cd "$ROOT" && cd "${AMEX_DIR_FLAG:-../../java/amex-agent}" 2>/dev/null \
                    && pwd)" \
    || { echo "amex-agent checkout not found; pass --amex-dir <path>" >&2; exit 1; }
  # Created by the host user the agent runs as, so the agent can write the uploaded statement;
  # compose needs its path for every e2e call, the checks below included.
  export E2E_STATEMENTS_DIR E2E_AUTH_DIR
  E2E_STATEMENTS_DIR="$(mktemp -d)"
  # Both containers run as this user and read the public key and the callers file from the first
  # folder; the private key stays in the second, which no container mounts.
  E2E_AUTH_DIR="$(mktemp -d)"
  E2E_PRIVATE_DIR="$(mktemp -d)"
  trap 'rm -rf "$E2E_STATEMENTS_DIR" "$E2E_AUTH_DIR" "$E2E_PRIVATE_DIR"' EXIT
  "$VENV/bin/python" "$ROOT/scripts/tests/e2e/make_auth.py" "$E2E_AUTH_DIR" "$E2E_PRIVATE_DIR"
  # The manager container mounts this registry in place of the development one.
  export CARD_AGENTS_FILE="$E2E_AUTH_DIR/card-agents.yaml"
  # A running e2e stack has already learnt the club, so this run would fail misleadingly.
  if [ -n "$(e2e_compose ps -q)" ]; then
    echo "The hfm-e2e stack is already up; remove it first:" \
      "docker compose -p hfm-e2e down -v" >&2
    exit 1
  fi
  if [ -n "$(compose ps --status running -q)" ]; then
    echo "The development stack is up on the same ports; stop it first:" \
      "./scripts/docker-helper.sh --stop" >&2
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
  "$VENV/bin/python" "$ROOT/scripts/tests/e2e/run_review.py" http://localhost:8010 "$statement" \
    "$E2E_PRIVATE_DIR/auth-private.pem" || status=$?
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
