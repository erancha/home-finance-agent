# 0005. Run as a Docker Compose stack on one machine

- Status: Accepted
- Date: 2026-10-15

## Context

The agent serves a household and is a demonstration of a design, run on a developer's machine.
It needs a web backend, a Postgres database (ADR 0003) and the React page, and its card agent,
amex-agent, is a Java service in another repository. A developer should bring all of it up with
one command and the same versions on any machine.

## Decision

- Docker Compose runs the stack: Postgres, a one-shot migration service, the FastAPI backend on
  uvicorn, which also serves the built React page on port 8010, and amex-agent built from its
  checkout beside this repository.
- One image holds the backend and the page; the Dockerfile builds the page with Node and installs
  the backend under the pinned `backend/requirements.txt`.
- One script brings the stack up and returns once it answers; the agent can also run as a local
  process beside the database in Docker, for fast restarts and a debugger.
- There is no cloud deployment.

## Consequences

- Docker is the one requirement to run the agent; Python and Node.js on the machine serve the
  tests and the local process.
- Postgres is published on the loopback address only.
