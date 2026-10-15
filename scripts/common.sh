#!/usr/bin/env bash
# Shared helpers for the home-finance-agent scripts: repo paths, help text, backend/.env loading
# and the card-agent path check, the compose wrapper, and backend venv provisioning.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
ENV_FILE="$BACKEND/.env"
COMPOSE_FILE="$ROOT/docker-compose.yml"
E2E_COMPOSE_FILE="$ROOT/docker-compose.e2e.yml"
# The agent container runs as the host user so uploads into the statements folder belong to it.
export HOST_UID HOST_GID
HOST_UID="$(id -u)" HOST_GID="$(id -g)"

# Print the calling script's header comment block as --help text (single source of usage docs).
print_help() { awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"; }

require_env() {
  [ -f "$ENV_FILE" ] \
    || { echo "backend/.env not found; create it first:  ./scripts/init-env.sh" >&2; exit 1; }
}

# Both paths come from backend/.env or the caller's environment and are relative to the repo root
# unless absolute; compose resolves them from there too, since it runs with the repo root as its
# project directory. Neither has a default: a blank one stops the script by name.
require_agent_paths() {
  local name
  for name in AMEX_AGENT_DIR AMEX_STATEMENTS_DIR; do
    [ -n "${!name:-}" ] || { echo "$name is blank; set it in backend/.env." >&2; exit 1; }
  done
}

# Export the keys of backend/.env as defaults, so compose interpolation and host processes see the
# same values: a variable the caller already exported keeps its value, even when the .env line is
# blank. Accepts blank lines, # comments and KEY=value (one matching pair of quotes is stripped);
# any other line is rejected rather than executed. The card-agent repo's load_env follows the
# same rule.
load_env() {
  local line key value lineno=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    lineno=$((lineno + 1))
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ ! "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      echo "$ENV_FILE:$lineno: expected KEY=value, got: $line" >&2
      exit 1
    fi
    key="${line%%=*}"
    value="${line#*=}"
    if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then
      value="${BASH_REMATCH[1]}"
    fi
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$ENV_FILE"
  require_agent_paths
}

abs_from_root() { (cd "$ROOT" && cd "$1" && pwd); }  # path

# The home finance agent reaches amex-agent here, outside Docker; the container listens on the
# same port.
AGENT_PORT=8020
AGENT_BASE="http://localhost:$AGENT_PORT"

amex_env_file() { echo "$(abs_from_root "$AMEX_AGENT_DIR")/.env"; }

# The bearer token the agent expects, from its own .env; empty when the key has no value.
amex_token() { sed -n 's/^APP_A2A_TOKEN=//p' "$(amex_env_file)"; }

# Requires load_env. A token that drifted makes every review fail at the agent's auth check, far
# from the cause, so the launch refuses instead.
require_matching_token() {
  local agent_env
  agent_env="$(amex_env_file)"
  [ -f "$agent_env" ] \
    || { echo "$agent_env not found; run ./scripts/init-env.sh --force" >&2; exit 1; }
  [ -n "$(amex_token)" ] || { echo "$agent_env has no APP_A2A_TOKEN value." >&2; exit 1; }
  if [ "$(amex_token)" != "${AMEX_AGENT_TOKEN:-}" ]; then
    echo "AMEX_AGENT_TOKEN in $ENV_FILE differs from APP_A2A_TOKEN in $agent_env;" \
      "run ./scripts/init-env.sh --sync-token (or --force to recreate backend/.env)." >&2
    exit 1
  fi
}

require_docker() {
  docker info >/dev/null 2>&1 \
    || { echo "Docker is not reachable; start it and retry." >&2; exit 1; }
}

compose() { (cd "$ROOT" && docker compose -f "$COMPOSE_FILE" "$@"); }

# The venv is current only when it was installed from pyproject.toml as it stands now: the stamp is
# a copy taken after the last successful install, so editing the dependency list forces a
# reinstall. The import and executable probe still catches a venv broken with the stamp intact.
ensure_venv() {
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  local stamp="$VENV/.pyproject.stamp"
  if ! cmp -s "$BACKEND/pyproject.toml" "$stamp" \
     || ! { "$VENV/bin/python" -c "import hfm" 2>/dev/null \
            && [ -x "$VENV/bin/uvicorn" ] && [ -x "$VENV/bin/pytest" ]; }; then
    echo "Installing backend dependencies into backend/.venv..."
    ( cd "$BACKEND" && "$VENV/bin/pip" install --quiet --disable-pip-version-check -e ".[dev]" )
    cp "$BACKEND/pyproject.toml" "$stamp"
  fi
}

# Waits up to about a minute for the URL to answer 2xx.
wait_for_url() {  # url
  curl -fs --retry 60 --retry-all-errors --retry-delay 1 --max-time 2 -o /dev/null "$1"
}
