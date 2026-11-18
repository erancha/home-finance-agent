# 0006. Several backend replicas behind an nginx edge, joined by Redis

- Status: Accepted
- Date: 2026-10-22

## Context

The backend container published port 8010 itself, so exactly one container could serve the page.
Live review events went through an in-process bus, so a browser's event stream had to be served
by the very process running its review. The agent is meant to serve many households, and a
review must outlive the replica that started it.

## Decision

- An nginx service, the edge, is the only one that publishes port 8010 and spreads requests over
  the backend replicas; the backend publishes no port.
- Compose runs the backend as two replicas on one Postgres and one Redis.
- `REDIS_URL` selects a Redis publish/subscribe bus that carries each review's events between
  replicas; unset, the in-process bus serves a single process, as when the agent runs on the host.
- What a review needs lives outside any process: the event log and checkpoints in Postgres, the
  sign-in in a cookie, live events in Redis.

## Consequences

- Any replica can serve any request: a stream shows the whole review whichever replica runs it,
  and an answer resumes a paused review from its checkpoint on whichever replica receives it.
- Replicas must coordinate what one process did alone, such as two answers to one review sent at
  once; `docs/architecture/scaling.md` states these rules.
- The end-to-end test runs one replica, since it answers a question the instant it arrives.
