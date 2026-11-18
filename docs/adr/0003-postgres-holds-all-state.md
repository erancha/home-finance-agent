# 0003. One Postgres database holds every review's state

- Status: Accepted
- Date: 2026-10-15

## Context

A review keeps several kinds of state: its own row and status, a log of every step the page
renders, the review graph's checkpoints (ADR 0002) and the categories a person chose for
merchants, which later months reuse. LangGraph ships a Postgres checkpointer. The agent runs as a
small Docker Compose stack (ADR 0005), where one more database server is one more service to run.

## Decision

- One Postgres 16 database holds the reviews, their event logs, LangGraph's checkpoints and the
  merchant memory, reached through SQLAlchemy with psycopg.
- Alembic migrations create and change this agent's tables; they run as a one-shot service
  before the agent starts.
- A review's id is the graph's thread id, so its checkpoints are found from the review row
  without a foreign key.

## Consequences

- One backup, one connection setting and one database to inspect (`sql-helper.sh`).
- A unique index keeps one standing review per month, and the event log is ordered by a
  per-review sequence number, both enforced by the database.
- LangGraph's checkpoint tables follow its own schema, which this agent does not design.
- Tests that touch storage run on a real Postgres through Testcontainers, so Docker must run.
