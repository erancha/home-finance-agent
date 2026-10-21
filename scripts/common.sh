#!/usr/bin/env bash
# Shared helpers for the home-finance-agent scripts: repo paths, help text, backend/.env loading,
# the card-agent registry path, the compose wrapper, and backend venv provisioning.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
ENV_FILE="$BACKEND/.env"
COMPOSE_FILE="$ROOT/docker-compose.yml"
E2E_COMPOSE_FILE="$ROOT/docker-compose.e2e.yml"
# The card-agent registry scripts/add-card-agent.sh writes and the manager loads (its
# CARD_AGENTS_FILE setting defaults to this path, relative to the repo root).
REGISTRY_FILE_NAME=card-agents.yaml
REGISTRY_FILE="$BACKEND/$REGISTRY_FILE_NAME"
# Print the calling script's header comment block as --help text (single source of usage docs).
print_help() { awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"; }

require_env() {
  [ -f "$ENV_FILE" ] \
    || { echo "backend/.env not found; create it first:  ./scripts/init-env.sh" >&2; exit 1; }
}

# Export the keys of backend/.env as defaults, so compose interpolation and host processes see the
# same values: a variable the caller already exported keeps its value, even when the .env line is
# blank. Accepts blank lines, # comments and KEY=value (one matching pair of quotes is stripped);
# any other line is rejected rather than executed.
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
  # Compose bind-mounts the registry by this path on every call, stop and logs included; a mount
  # of a missing path would create a directory there, so a launch checks the file exists first.
  : "${CARD_AGENTS_FILE:=$REGISTRY_FILE}"
  export CARD_AGENTS_FILE
  # The registry is readable by its owner alone, so compose runs the manager as that user: the ids
  # are exported for every compose call, since the file is mounted on each.
  : "${HOST_UID:=$(id -u)}" "${HOST_GID:=$(id -g)}"
  export HOST_UID HOST_GID
}

# Requires load_env. init-env.sh writes an empty registry so the mount has a file to bind.
require_registry() {
  [ -f "$CARD_AGENTS_FILE" ] \
    || { echo "$CARD_AGENTS_FILE not found; create it:  ./scripts/init-env.sh" >&2; exit 1; }
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
