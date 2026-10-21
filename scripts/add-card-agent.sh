#!/usr/bin/env bash
#
# Connect a card agent, or replace its entry: the URL this agent calls it at, the URL a person's
# browser opens its pages at, and the secret the card agent's operator issued to this agent.
# Writes backend/card-agents.yaml (mode 600, gitignored) in the shape the manager loads:
#
#   agents:
#     - name: <name>
#       url: <url>
#       browser_url: <browser url>
#       shared_secret: <secret>
#
#   ./scripts/add-card-agent.sh --name N --url U --browser-url B --secret S
#   ./scripts/add-card-agent.sh ... --file <path>    # another registry than CARD_AGENTS_FILE
#
# An agent with that name is replaced; other agents are kept. Removing an entry disconnects the
# agent; the manager reads the file at startup, so run ./scripts/start.sh after a change.
#
# A card agent's registration script prints the name, url, browser url and secret; its start
# script repeats the first three. --url is where the manager fetches the agent's card; the
# calls then go to the URL the card advertises, so the two must agree and both must be reachable
# from where the manager runs: http://host.docker.internal:<port> for an agent on this machine when
# the manager runs in Docker, http://localhost:<port> when it runs with start.sh --host.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

# The registry start.sh mounts: CARD_AGENTS_FILE from backend/.env when set, else the default.
[ -f "$ENV_FILE" ] && load_env
NAME="" URL="" BROWSER_URL="" SECRET="" FILE="${CARD_AGENTS_FILE:-$REGISTRY_FILE}"
while [ $# -gt 0 ]; do
  case "$1" in
    --name)        NAME="${2?--name needs a value}"; shift ;;
    --url)         URL="${2?--url needs a value}"; shift ;;
    --browser-url) BROWSER_URL="${2?--browser-url needs a value}"; shift ;;
    --secret)      SECRET="${2?--secret needs a value}"; shift ;;
    --file)        FILE="${2?--file needs a path}"; shift ;;
    -h|--help)     print_help; exit 0 ;;
    *) echo "Usage: ./scripts/add-card-agent.sh --name N --url U --browser-url B --secret S" \
            "[--file F]" >&2; exit 2 ;;
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
python3 - "$FILE" "$NAME" "$URL" "$BROWSER_URL" "$SECRET" <<'PY'
import os, re, sys

path, name, url, browser_url, secret = sys.argv[1:]
FIELDS = ("url", "browser_url", "shared_secret")
ENTRY = re.compile(r"^  - name: (\S+)$")
FIELD = re.compile(r"^    (url|browser_url|shared_secret): (\S+)$")

# Reads back only the shape this script writes, plus the empty registry init-env.sh writes;
# anything else is refused rather than guessed at.
agents = []
if os.path.exists(path):
    current = None
    for number, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#") or line in ("agents:", "agents: []"):
            continue
        if entry := ENTRY.match(line):
            current = {"name": entry.group(1)}
            agents.append(current)
        elif (field := FIELD.match(line)) and current is not None:
            current[field.group(1)] = field.group(2)
        else:
            sys.exit(f"{path}:{number}: not a line add-card-agent.sh writes: {line}")
    for agent in agents:
        if set(agent) != {"name", *FIELDS}:
            sys.exit(f"{path}: entry {agent.get('name')} lacks one of {', '.join(FIELDS)}")

agents = [a for a in agents if a["name"] != name]
agents.append({"name": name, "url": url, "browser_url": browser_url, "shared_secret": secret})
HEADER = "# Card agents this home finance agent reviews with; written by scripts/add-card-agent.sh."
lines = [HEADER, "agents:"]
for agent in agents:
    lines.append(f"  - name: {agent['name']}")
    lines += [f"    {field}: {agent[field]}" for field in FIELDS]
with open(path, "w", encoding="utf-8") as out:
    out.write("\n".join(lines) + "\n")
os.chmod(path, 0o600)
PY
echo "Connected $NAME in $FILE. The manager reads it at startup: ./scripts/start.sh applies it."
