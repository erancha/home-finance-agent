#!/usr/bin/env bash
#
# Connect a card agent, or replace its entry: the URL this agent calls it at, the URL a person's
# browser opens its pages at, and the secret the card agent's operator issued to this agent.
# Writes the registry of this machine, backend/card-agents.yaml, or with --ec2 as the first
# argument the EC2 instance's, backend/card-agents.ec2.yaml (both mode 600, gitignored), in the
# shape the manager loads:
#
#   agents:
#     - name: <name>
#       url: <url>
#       browser_url: <browser url>
#       shared_secret: <secret>
#
#   ./scripts/tools/add-card-agent.sh [--ec2] --name N --url U --browser-url B --secret S
#   ./scripts/tools/add-card-agent.sh ... --file <path>    # another registry
#
# An agent with that name is replaced; other agents are kept. Removing an entry disconnects the
# agent; the manager reads the registry at startup, so run ./scripts/deploy.sh (with --ec2 for the
# instance's) after a change.
#
# A card agent's registration script prints the name, url, browser url and secret; its deploy
# script repeats the first three. --url is where the manager fetches the agent's card; the calls
# then go to the URL the card advertises, and both must be reachable from the manager's container:
# http://host.docker.internal:<port> for an agent on the same machine, or on the same EC2
# instance. --browser-url is where a person's browser opens the agent's pages: on this machine its
# localhost address, on the instance its CloudFront address, which its own deploy prints.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/common.sh"

FILE="$REGISTRY_FILE" DEPLOY="./scripts/deploy.sh"
if [ "${1:-}" = --ec2 ]; then FILE="$EC2_REGISTRY_FILE" DEPLOY+=" --ec2"; shift; fi
NAME="" URL="" BROWSER_URL="" SECRET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name)        NAME="${2?--name needs a value}"; shift ;;
    --url)         URL="${2?--url needs a value}"; shift ;;
    --browser-url) BROWSER_URL="${2?--browser-url needs a value}"; shift ;;
    --secret)      SECRET="${2?--secret needs a value}"; shift ;;
    --file)        FILE="${2?--file needs a path}"; shift ;;
    -h|--help)     print_help; exit 0 ;;
    *) echo "Usage: ./scripts/tools/add-card-agent.sh [--ec2] --name N --url U --browser-url B" \
            "--secret S [--file F]" >&2; exit 2 ;;
  esac
  shift
done
for pair in "--name=$NAME" "--url=$URL" "--browser-url=$BROWSER_URL" "--secret=$SECRET"; do
  [ -n "${pair#*=}" ] || { echo "${pair%%=*} is required and must not be blank." >&2; exit 2; }
done
# The file is rewritten from these values, so each must be a plain YAML scalar.
for value in "$NAME" "$SECRET"; do
  [[ "$value" =~ ^[A-Za-z0-9_.-]+$ ]] \
    || { echo "Names and secrets may contain only letters, digits, '_', '.' and '-': '$value'." >&2
         exit 2; }
done
for value in "$URL" "$BROWSER_URL"; do
  [[ "$value" =~ ^https?://[A-Za-z0-9_.:/?\&=%-]+$ ]] \
    || { echo "URLs must be http(s) and contain no spaces or quotes: '$value'." >&2; exit 2; }
done

umask 077
python3 "$SCRIPT_DIR/tools/add_card_agent.py" "$FILE" "$NAME" "$URL" "$BROWSER_URL" "$SECRET"
echo "Connected $NAME in $FILE. The manager reads it at startup: $DEPLOY applies it."
