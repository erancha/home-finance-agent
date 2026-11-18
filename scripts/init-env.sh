#!/usr/bin/env bash
#
# Create the gitignored settings files under scripts/lib/ (secrets.sh, params.sh and
# aws-config.sh) from their .example.sh files, with the generated values, and the gitignored files
# beside them: an empty card-agent registry for this machine and one for the EC2 instance, and
# config/budget.yaml from config/budget.example.yaml. An existing settings file is kept unless
# --force; an existing registry or budget is always kept.
#
#   ./scripts/init-env.sh             # create each file that is missing
#   ./scripts/init-env.sh --force     # replace every settings file, hand-filled keys included
#
# In secrets.sh the database password is 32 hex characters from openssl, and the agent's database
# URL is written from the ports and database names of scripts/lib/stack-params.sh. LLM_API_KEY of
# secrets.sh, and LLM_MODEL and GOOGLE_CLIENT_ID of params.sh, stay blank for you to fill in
# (docs/sign-in.md for the last). Each settings file and registry is readable by its owner only. If
# a written value fails its check, the settings files stay as they were. Put your monthly limits
# in config/budget.yaml, then run ./scripts/deploy.sh; connect a card agent later with
# ./scripts/tools/add-card-agent.sh, since the manager runs without any.
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

# shellcheck source=lib/stack-params.sh
source "$STACK_PARAMS_FILE"

# Each new file is built and verified beside its target and renamed over it only when all are
# complete, so a failure leaves no partial file. mktemp creates a draft readable by the owner
# only, as the files hold secrets.
drafts=()
trap 'rm -f "${drafts[@]}"' EXIT
draft_of() {  # target; prints the draft's path, or nothing when the target is kept
  local target="$1" draft
  if [ -f "$target" ] && [ "$FORCE" -eq 0 ]; then
    echo "${target#"$ROOT"/} already exists; left as it is (--force overwrites it)." >&2
    return
  fi
  draft="$(mktemp "$target.XXXXXX")"
  cat "${target%.sh}.example.sh" > "$draft"
  printf '%s' "$draft"
}

secrets_draft="$(draft_of "$SECRETS_FILE")"
[ -z "$secrets_draft" ] || drafts+=("$secrets_draft")
params_draft="$(draft_of "$PARAMS_FILE")"
[ -z "$params_draft" ] || drafts+=("$params_draft")
# Only deploy.sh --ec2 reads it, so it may stay unfilled on a machine that deploys locally.
aws_draft="$(draft_of "$AWS_CONFIG_FILE")"
[ -z "$aws_draft" ] || drafts+=("$aws_draft")

if [ -n "$secrets_draft" ]; then
  db_password="$(openssl rand -hex 16)"
  database_url="postgresql+psycopg://$POSTGRES_USER:$db_password"
  database_url+="@127.0.0.1:$DB_HOST_PORT/$POSTGRES_DB"
  sed -i "s|^export POSTGRES_PASSWORD=.*|export POSTGRES_PASSWORD=\"$db_password\"|;
          s|^export DATABASE_URL=.*|export DATABASE_URL=\"$database_url\"|" "$secrets_draft"
  for key in POSTGRES_PASSWORD DATABASE_URL; do
    # The draft is sourced in a subshell, so a key the example lacks reads as unset here.
    ( unset "$key"
      # shellcheck source=/dev/null
      source "$secrets_draft"
      [ -n "${!key:-}" ] ) \
      || { echo "$key has no value in the new ${SECRETS_FILE#"$ROOT"/}" >&2; exit 1; }
  done
fi

[ -z "$secrets_draft" ] || mv "$secrets_draft" "$SECRETS_FILE"
[ -z "$params_draft" ] || mv "$params_draft" "$PARAMS_FILE"
[ -z "$aws_draft" ] || mv "$aws_draft" "$AWS_CONFIG_FILE"
[ -z "$secrets_draft" ] \
  || echo "Created scripts/lib/secrets.sh with a generated database password."
[ -z "$params_draft" ] || echo "Created scripts/lib/params.sh."
[ -z "$aws_draft" ] || echo "Created scripts/lib/aws-config.sh (needed for deploy.sh --ec2 only)."

# A registry holds the card agents' secrets once one is connected, so only its owner may read it.
for registry in "$REGISTRY_FILE" "$EC2_REGISTRY_FILE"; do
  [ ! -f "$registry" ] || continue
  ( umask 077 && printf 'agents: []\n' > "$registry" )
  echo "Created ${registry#"$ROOT"/} with no card agents."
done
# The budget is the person's own, so it is never overwritten, not even by --force.
if [ ! -f "$BUDGET_FILE" ]; then
  cp "$BUDGET_EXAMPLE" "$BUDGET_FILE"
  echo "Created config/budget.yaml from the example; put your monthly limits in it."
fi
# The reminder is for a file this run created; a kept file was filled in before.
if [ -n "$secrets_draft$params_draft" ]; then
  echo "Fill in the settings left blank (docs/sign-in.md for GOOGLE_CLIENT_ID);" \
       "./scripts/deploy.sh names each one it still needs."
fi
