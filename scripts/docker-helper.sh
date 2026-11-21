#!/usr/bin/env bash
#
# Docker Compose helper for the stack: teardown, logs, status. Bringing it up is deploy.sh's job.
# With --ec2 as the first argument it acts on the stack's EC2 instance instead of this machine.
#
#   ./scripts/docker-helper.sh --stop [--volumes]
#       Stop and remove the stack's containers and network. The hfm_pgdata volume (reviews,
#       events, checkpoints, merchant memory) is KEPT by default so it survives a restart;
#       --volumes (alias -v) also removes it for a clean database.
#   ./scripts/docker-helper.sh --logs [-e|--errors] [service...]
#       Follow the stack's logs live (last 200 lines). -e filters to ERROR/EXCEPTION/FATAL lines.
#       A trailing service list (db redis migrate manager edge) narrows to those services.
#   ./scripts/docker-helper.sh --ps
#       Show the containers' status.
#   ./scripts/docker-helper.sh --costs [--since <age>]
#       The model calls of the stack's logs by UTC day and by kind of call: calls, tokens in and
#       out, dollars at the prices in model_costs.py, which a provider price change does not reach
#       until the table is updated and deployed. <age> is 30m, 6h or 2d (default 1h). The logs
#       are those of the containers now running: a container a deploy recreated starts its log
#       anew.
#   ./scripts/docker-helper.sh --ec2 --delete-stack
#       Delete this repo's EC2 stack of the git branch: its port on the instance and its
#       CloudFront distribution, after asking to type the stack's name. Its containers and the
#       database volume stay on the instance; run --ec2 --stop [--volumes] first to remove them.
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
  case "${1:-}" in
    -e|--errors) shift; compose logs -f --tail=200 "$@" | grep -Eai '(error|exception|fatal)' ;;
    *)           compose logs -f --tail=200 "$@" ;;
  esac
}

# Docker reads --since as a duration in hours, minutes or seconds; a count of days becomes hours,
# so --costs --since 2d reads as it does in the AWS repos.
do_costs() {
  local since=1h
  case "$#:${1:-}" in
    0:) ;;
    2:--since) since="$2" ;;
    *) echo "--costs takes only --since <age>: $*" >&2; exit 2 ;;
  esac
  if [[ "$since" =~ ^([0-9]+)d$ ]]; then since="$((BASH_REMATCH[1] * 24))h"; fi
  compose logs --no-color --no-log-prefix --timestamps --since "$since" |
    python3 "$SCRIPT_DIR/lib/docker_helper.py"
  echo "The dollars use the prices in PRICE_PER_MILLION of model_costs.py, as last deployed." >&2
}

TARGET=local
if [ "${1:-}" = --ec2 ]; then TARGET=ec2; shift; fi
mode="${1:-}"
case "$mode" in
  -h|--help) print_help; exit 0 ;;
  "")        print_help; exit 1 ;;
esac
shift

load_settings
if [ "$mode" = --delete-stack ]; then
  [ "$TARGET" = ec2 ] || { echo "--delete-stack needs --ec2 before it" >&2; exit 2; }
  delete_ec2_stack
  exit 0
fi
if [ "$TARGET" = ec2 ]; then use_ec2; fi
require_docker
case "$mode" in
  --stop) do_stop "$@" ;;
  --logs) do_logs "$@" ;;
  --ps)   compose ps "$@" ;;
  --costs) do_costs "$@" ;;
  *) echo "Unknown command: $mode (expected --stop | --logs | --ps | --costs | --delete-stack;" \
       "see -h)" >&2
     exit 1 ;;
esac
