#!/usr/bin/env bash
# Shared helpers for the home-finance-agent scripts: repo paths, help text, the settings files
# under scripts/lib/, the card-agent registries, compose access, and backend venv provisioning.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
BACKEND_VENV="$BACKEND/.venv"
FRONTEND="$ROOT/frontend"
# The stack's settings: stack-params.sh is committed; params.sh (this deployment's own settings)
# and secrets.sh are gitignored and created by init-env.sh from their .example.sh files.
STACK_PARAMS_FILE="$ROOT/scripts/lib/stack-params.sh"
PARAMS_FILE="$ROOT/scripts/lib/params.sh"
SECRETS_FILE="$ROOT/scripts/lib/secrets.sh"
# The deploying user's AWS credentials and region, read only for the EC2 target.
AWS_CONFIG_FILE="$ROOT/scripts/lib/aws-config.sh"
# The card agents the manager calls, with the secrets they issued to it: one registry for this
# machine and one for the EC2 instance, where each card agent's browser address differs.
# tools/add-card-agent.sh writes them and init-env.sh creates them empty; both are gitignored.
REGISTRY_FILE="$BACKEND/card-agents.yaml"
EC2_REGISTRY_FILE="$BACKEND/card-agents.ec2.yaml"
# The person's budget, never committed; init-env.sh starts it from the example beside it.
BUDGET_FILE="$ROOT/config/budget.yaml"
BUDGET_EXAMPLE="$ROOT/config/budget.example.yaml"
# The Compose files of the target: docker-compose.yml alone on this machine; use_ec2 of
# lib/ec2.sh adds the instance's override.
COMPOSE_FILES=("$ROOT/docker-compose.yml")
# Print the calling script's header comment block as --help text (single source of usage docs).
print_help() { awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"; }

# shellcheck source=lib/settings-guard.sh
source "$ROOT/scripts/lib/settings-guard.sh"
# shellcheck source=lib/ec2.sh
source "$ROOT/scripts/lib/ec2.sh"

# Exports every setting of the three files into this shell, which is where docker compose takes
# the ${...} values and each service's keys from. Stops when a gitignored file is missing, when
# git tracks it, or when a tracked file holds one of its secrets or addresses.
load_settings() {
  # shellcheck source=lib/stack-params.sh
  source "$STACK_PARAMS_FILE"
  source_checked_file "$PARAMS_FILE" assert_addresses_untracked
  source_checked_file "$SECRETS_FILE" assert_secrets_untracked
}

# Adds each listed setting that is blank or still its example's <placeholder> to
# MISSING_SETTINGS, with the file under scripts/lib/ that sets it, so one run names them all.
MISSING_SETTINGS=()
collect_missing_settings() {  # file key...
  local file="$1" key
  shift
  for key in "$@"; do
    [[ -n "${!key:-}" && "${!key}" != "<"*">" ]] || MISSING_SETTINGS+=("$key ($file)")
  done
}

# Stops when collect_missing_settings found any, listing every one of them.
require_collected_settings() {
  [ "${#MISSING_SETTINGS[@]}" -eq 0 ] && return
  echo "Fill in these settings under scripts/lib/, then run the script again:" >&2
  printf '  %s\n' "${MISSING_SETTINGS[@]}" >&2
  exit 1
}

require_docker() {
  docker info >/dev/null 2>&1 \
    || { echo "Docker is not reachable; start it and retry." >&2; exit 1; }
}

# Compose reads the ${...} values and the keys each service lists in its environment from this
# shell, so the settings are loaded first. Both registries are exported on every call:
# docker-compose.yml hands the manager the one of this machine, docker-compose.ec2.yml the
# instance's. REGISTRY_FILE may be pointed elsewhere first, as test.sh e2e does.
compose() {
  load_settings
  local registry
  for registry in "$REGISTRY_FILE" "$EC2_REGISTRY_FILE"; do
    [ -f "$registry" ] ||
      die "${registry#"$ROOT"/} not found; create it first:  ./scripts/init-env.sh"
  done
  CARD_AGENTS_REGISTRY="$(< "$REGISTRY_FILE")"
  CARD_AGENTS_EC2_REGISTRY="$(< "$EC2_REGISTRY_FILE")"
  export CARD_AGENTS_REGISTRY CARD_AGENTS_EC2_REGISTRY
  local file
  local -a files=()
  for file in "${COMPOSE_FILES[@]}"; do files+=(-f "$file"); done
  (cd "$ROOT" && docker compose "${files[@]}" "$@")
}

# Waits up to about a minute until the URL answers 2xx: the edge answers 502 while no manager
# replica is up, which is no answer from the manager.
wait_for_http() {  # url
  curl -fs --retry 60 --retry-all-errors --retry-delay 1 --max-time 2 -o /dev/null "$1"
}

# The venv holds the runtime dependencies at the exact pins the image installs (requirements.txt
# as a constraint), so the suite runs on what ships; the dev tools float within pyproject.toml. It
# is current only when installed from both files as they stand now: the stamp is a copy taken
# after the last successful install, so editing either forces a reinstall. The import and
# executable probe still catches a venv broken with the stamp intact.
ensure_backend_venv() {
  [ -d "$BACKEND_VENV" ] || python3 -m venv "$BACKEND_VENV"
  local stamp="$BACKEND_VENV/.dependencies.stamp"
  if ! cat "$BACKEND/pyproject.toml" "$BACKEND/requirements.txt" | cmp -s - "$stamp" \
     || ! { "$BACKEND_VENV/bin/python" -c "import hfm" 2>/dev/null \
            && [ -x "$BACKEND_VENV/bin/uvicorn" ] && [ -x "$BACKEND_VENV/bin/pytest" ]; }; then
    echo "Installing backend dependencies into backend/.venv..."
    ( cd "$BACKEND" && "$BACKEND_VENV/bin/pip" install --quiet --disable-pip-version-check \
        --constraint requirements.txt -e ".[dev]" )
    cat "$BACKEND/pyproject.toml" "$BACKEND/requirements.txt" > "$stamp"
  fi
}

# Requires load_settings. deploy.sh prints this as it brings the manager up: what a card agent's
# operator needs to register this agent as a caller, so no card agent's docs repeat it. The client
# id is public.
print_handover() {
  echo "Hand this to each card agent's operator, who registers this agent as a caller with it:"
  echo "  Google client id: $GOOGLE_CLIENT_ID"
}
