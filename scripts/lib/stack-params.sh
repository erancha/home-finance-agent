#!/usr/bin/env bash
# Settings of the Compose stack that are neither secret nor private, committed so every checkout
# runs the same stack. Sourced by scripts/common.sh, never executed; the agent started on the host
# reads it too (backend/src/hfm/platform/config.py), so every setting is one plain export line
# with a quoted value, which may name a key set above it as ${KEY}. Secrets are in secrets.sh and
# this deployment's own settings in params.sh, both gitignored.
#
# Compose hands each container only the keys it reads, listed per service in docker-compose.yml.
# A commented-out line shows an optional key at its default; uncomment it to set the key.

# ── Ports ────────────────────────────────────────────────────────────────────────
# Read by docker-compose.yml only: the port the edge publishes the page and the API on, on every
# interface of this machine, so other devices on the network reach it too; localhost at this port
# is the origin Google sign-in is registered for. It must be free on the host.
export EDGE_HOST_PORT="8010"
# Read by docker-compose.yml only: the port Postgres listens on inside its container.
export DB_PORT="5432"
# Read by docker-compose.yml only: the loopback port Postgres is published on, for an agent started
# on the host (DATABASE_URL of secrets.sh names it) or a psql on this machine. It must be free on
# the host.
export DB_HOST_PORT="5434"

# ── EC2 ──────────────────────────────────────────────────────────────────────────
# Read by scripts/lib/ec2.sh only, for deploy.sh --ec2. The stack's name on main; any other
# branch deploys EC2_STACK-fb.
export EC2_STACK="home-finance-agent"
# Used only when the stack is a host (EC2_HOST_STACK of params.sh blank): the instance's ARM
# type, sized for every stack it runs; a change stops and starts the same instance.
export EC2_INSTANCE_TYPE="t4g.small"
# The port CloudFront reaches this stack at on the instance; every stack on the instance has its
# own.
export EC2_ORIGIN_PORT="${EDGE_HOST_PORT}"

# ── Database ─────────────────────────────────────────────────────────────────────
# Read by docker-compose.yml only: the Postgres user and database the agent's tables live in; also
# read by init-env.sh and tools/sql-helper.sh, and set when the database volume is first created.
export POSTGRES_USER="hfm"
export POSTGRES_DB="hfm"

# ── Language model ───────────────────────────────────────────────────────────────
# How many days a written report keeps answering for the same totals instead of the model; a
# person's older reports are forgotten when their next one is written.
# export REPORT_MEMORY_RETENTION_DAYS="90"

# ── Sign-in ──────────────────────────────────────────────────────────────────────
# The issuer every ID token must name; docker-compose.e2e.yml points it at a test issuer.
# export AUTH_ISSUER="https://accounts.google.com"
# Where the issuer publishes the keys that sign its tokens.
# export AUTH_JWKS_URL="https://www.googleapis.com/oauth2/v3/certs"
# True where people reach the agent only over HTTPS that ends before it, so the sign-in cookie is
# marked Secure; docker-compose.ec2.yml sets it for the EC2 instance behind CloudFront.
# export HFM_HTTPS_ONLY="false"
# Tests only: a PEM public key file that verifies tokens instead of the published keys, so a test
# signs its own tokens and never reaches Google.
# export AUTH_PUBLIC_KEY_FILE=""
# Tests only: docker-compose.e2e.yml sets it, so the end-to-end test shows a canned report and
# reads neither LLM_MODEL nor LLM_API_KEY.
# export HFM_E2E="false"

# ── Files ────────────────────────────────────────────────────────────────────────
# For an agent started on the host only, relative to the repo root: the card-agent registry
# (tools/add-card-agent.sh writes it; absent means no card agents) and the monthly budget. In
# Compose the registry reaches the manager as a secret and the budget is baked into the image, so
# compose passes neither key.
# export CARD_AGENTS_FILE="backend/card-agents.yaml"
# export BUDGET_CONFIG="config/budget.yaml"
# The built page's folder. The image sets it to its own copy and compose does not pass this key.
# An agent started on the host sets it to frontend/dist, or leaves it unset to serve the API only.
# export HFM_FRONTEND_DIST=""

# ── Logging ──────────────────────────────────────────────────────────────────────
# The root log level, and per-module overrides (none by default; the example shows the shape).
# The logging setup reads both from the process environment, so compose passes them and an agent
# started on the host takes them only when they are exported in its shell.
# export HFM_LOG_LEVEL="WARNING"
# export HFM_LOG_LEVELS="hfm.application.review_graph=DEBUG"
