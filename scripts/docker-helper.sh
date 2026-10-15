#!/usr/bin/env bash
#
# Docker Compose helper for the stack: teardown, logs, status. Bringing it up is start.sh's job.
#
#   ./scripts/docker-helper.sh --stop [--volumes]
#       Stop and remove the stack's containers and network. Volumes are KEPT by default so the
#       Postgres data (reviews, merchant memory) survives a restart; --volumes (alias -v) also
#       removes them for a clean database.
#   ./scripts/docker-helper.sh --logs [-e|--errors] [service...]
#       Follow logs live (last 200 lines). -e filters to ERROR/EXCEPTION/FATAL lines. A trailing
#       service list (db migrate amex-agent manager) narrows to those services.
#   ./scripts/docker-helper.sh --ps
#       Show the stack's container status.
#   -h, --help
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

do_stop() {
  local -a down=(down --remove-orphans)
  while [ $# -gt 0 ]; do
    case "$1" in
      -v|--volumes) down+=(-v) ;;
      *) echo "Unknown --stop option '$1'" >&2; exit 1 ;;
    esac
    shift
  done
  compose "${down[@]}"
}

do_logs() {
  local pattern=""
  case "${1:-}" in
    -e|--errors) pattern='(error|exception|fatal)'; shift ;;
  esac
  if [ -n "$pattern" ]; then
    compose logs -f --tail=200 "$@" | grep -Eai "$pattern"
  else
    compose logs -f --tail=200 "$@"
  fi
}

mode="${1:-}"
case "$mode" in
  -h|--help) print_help; exit 0 ;;
  "")        print_help; exit 1 ;;
esac
shift

require_env
load_env
require_docker
case "$mode" in
  --stop) do_stop "$@" ;;
  --logs) do_logs "$@" ;;
  --ps)   compose ps "$@" ;;
  *) echo "Unknown command: $mode (expected --stop | --logs | --ps; see -h)" >&2; exit 1 ;;
esac
