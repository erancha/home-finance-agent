# API endpoints

This document details every route behind the entry points that
[Architecture](architecture.md#the-parts) summarizes: who may call it, what it takes and answers,
and its limits. The page reaches the `manager` replicas through the `edge` service over an HTTP
API and an event stream. The home finance agent serves no A2A endpoint: it is the A2A client of
the card agents, and the calls it makes to them are in [A2A contract](a2a-contract.md). The review
runs a route starts are workers ([Workers' responsibilities and flows](workers.md)).

## Manager HTTP API (`manager` service)

FastAPI in `backend/src/hfm/platform/` (`app.py` and the routers under `api/`). Every route under
`/api/` other than `GET /api/auth/config`, `POST /api/auth/session` and `DELETE /api/auth/session`
needs the sign-in cookie, answers 401 without a valid one, and acts only for the signed-in person
([Sign-in](sign-in.md#where-it-lives-in-the-code)). The review routes share their errors: 404 for
a review the person does not hold, cleared ones included; 409 when the review's status does not
allow the request, or when the month already has a standing review, whose id the body names; 422
for an answer set the runner refuses, with the `missing`, `unknown` and `invalid` question ids;
429 once the day's starts are used, with the time to wait in `Retry-After`.

Money travels as a decimal string with two places, and totals are computed on exact values before
it is formatted. The page and the report prompt both show whole amounts with thousands separators.

### Sign-in

- `GET /api/auth/config` — the public Google client id, for the page; no cookie needed.
- `POST /api/auth/session` — takes the Google ID token as `credential`, verifies it and sets the
  sign-in cookie; answers the person's id, email and name.
- `GET /api/auth/me` — the signed-in person.
- `DELETE /api/auth/session` — signs out by clearing the cookie (204).

### Card agents

- `GET /api/agents` — the names of the connected card agents, in registry order, so the page can
  say none is connected before a review starts.

### Reviews

- `POST /api/reviews` — starts a review of a month and answers its id (202); refused when the
  month has a standing review or the day's starts are used.
- `GET /api/reviews/{review_id}` — the review's month, status, open questions, totals and report.
- `GET /api/months/{month}` — the month's standing review, if any, and whether a start is allowed
  now.
- `DELETE /api/reviews/{review_id}` — clears a review that is not running, freeing its month
  (204).
- `POST /api/reviews/{review_id}/answers` — answers a waiting review's questions (204).
- `POST /api/reviews/{review_id}/categories` — chooses categories for merchants of a completed
  review, which reruns its totals and report (204).
- `GET /api/reviews/{review_id}/expected` — the charges a completed review's month still expects,
  projected from an earlier month.

### Event stream

- `GET /api/reviews/{review_id}/events` — the review's event log replayed, then live events, as
  server-sent events ([Events and the live stream](architecture/events.md#the-stream)).

### Probes and the page

- `GET /health` — answers while the process runs. The `manager` service's healthcheck calls it
  in each replica, the `edge` service's calls it through nginx, and `deploy.sh` returns once it
  answers through the edge.
- `GET /ready` — also needs the database to answer; 503 when it does not.

The built page is served at `/`, the same origin as the API, behind every route above.
