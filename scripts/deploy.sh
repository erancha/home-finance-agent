#!/usr/bin/env bash
#
# Deploy the home finance agent: build the images and start Postgres, Redis, the manager replicas
# and the nginx edge in Docker Compose, then return once the manager answers through the edge.
#
#   ./scripts/deploy.sh          on this machine's Docker
#   ./scripts/deploy.sh --ec2    on an EC2 instance, behind a CloudFront distribution of its own
#   -h, --help                   show this help
#
# Before the manager starts, a one-shot container (the migrate service) brings the Postgres tables
# up to the current schema with Alembic, then exits. The manager refuses to start when LLM_MODEL,
# LLM_API_KEY or GOOGLE_CLIENT_ID is blank, so the script checks them first, with the database
# settings, and names every one that is blank with its settings file. Every run starts with
# ./scripts/init-env.sh, which creates a missing settings file, registry or budget and keeps the
# existing ones, so a first run creates them all and then stops on the settings left to fill in.
# Stop or inspect the stack with ./scripts/docker-helper.sh (--stop / --logs / --ps), which takes
# --ec2 too.
#
# The manager reads its card agents from backend/card-agents.yaml (on EC2 from
# backend/card-agents.ec2.yaml) at startup, so rerun this script after connecting one with
# ./scripts/tools/add-card-agent.sh. As the manager comes up, the script prints this agent's
# Google client id, which a card agent's operator registers it as a caller with.
#
# On this machine the edge publishes the page and the API at localhost:EDGE_HOST_PORT, on every
# interface (localhost is the origin Google sign-in is registered for), and Postgres is published
# at 127.0.0.1:DB_HOST_PORT.
#
# --ec2 also needs the access key pair and region in scripts/lib/aws-config.sh, and deploys to
# the account its credentials belong to. The stack is the instance's host, unless EC2_HOST_STACK
# of params.sh names another Docker Compose repo's host stack, deployed first from its repo: then
# it is a guest on that stack's instance. This script creates or updates this repo's
# CloudFormation stack of scripts/template-ec2.yaml (the git branch selects it:
# home-finance-agent on main, home-finance-agent-fb on any other branch): the edge's port in
# the instance's security group and a CloudFront distribution whose https address is the only way
# in. It then builds the images here for ARM, loads them into the instance's Docker daemon over
# SSH, and runs Compose against that daemon. The settings files and the registries stay on this
# machine; each container's own settings, secrets included, reach the instance as part of the
# container's configuration, which Docker keeps on the instance's encrypted disk. Register the
# printed address with Google once (docs/sign-in.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

TARGET=local
case "${1:-}" in
  -h|--help) print_help; exit 0 ;;
  --ec2)     TARGET=ec2 ;;
  "")        ;;
  *)         print_help >&2; exit 2 ;;
esac

"$SCRIPT_DIR/init-env.sh"
load_settings
collect_missing_settings secrets.sh POSTGRES_PASSWORD DATABASE_URL LLM_API_KEY
collect_missing_settings params.sh LLM_MODEL GOOGLE_CLIENT_ID
require_collected_settings
require_docker

deploy_local() {
  local page="http://localhost:$EDGE_HOST_PORT"
  echo "Building and starting the database, Redis, the manager replicas and the edge..."
  compose up -d --build
  wait_for_http "$page/health" \
    || { echo "the manager did not answer on $page; see ./scripts/docker-helper.sh --logs" >&2
         exit 1; }
  echo "Open $page in your browser and sign in with Google (health: /health, ready: /ready)."
  echo "  stop it or tail logs:  ./scripts/docker-helper.sh --stop | --logs"
  print_handover
}

deploy_ec2() {
  load_aws_config
  resolve_ec2_stack
  deploy_ec2_stack
  resolve_ec2_host
  COMPOSE_FILES+=("$EC2_COMPOSE_FILE")

  echo "Building the images for linux/arm64 on this machine..."
  compose build
  prepare_ec2_host
  echo "Loading the images into the instance's Docker daemon..."
  # shellcheck disable=SC2046  # one image name per word, none with spaces
  docker save $(ec2_built_images) | gzip | ssh_ec2 "$EC2_HOST_USER@$EC2_HOST" 'gunzip | docker load'

  open_ec2_docker
  echo "Starting the database, Redis, the manager replicas and the edge on the instance..."
  compose up -d --no-build --remove-orphans
  # A deploy leaves the previous build's layers behind; the instance's disk is small.
  docker image prune -f >/dev/null
  wait_for_http "$EC2_URL/health" \
    || { echo "the manager did not answer on $EC2_URL/health;" \
              "see ./scripts/docker-helper.sh --ec2 --logs" >&2
         exit 1; }
  echo "The page answers at $EC2_URL (health: /health, ready: /ready)."
  echo "  Register it with Google once: $EC2_URL as an authorized JavaScript origin of the"
  echo "  OAuth client (docs/sign-in.md)."
  echo "  stop it or tail logs:  ./scripts/docker-helper.sh --ec2 --stop | --logs"
  print_handover
}

"deploy_$TARGET"
