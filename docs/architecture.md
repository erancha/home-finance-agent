# Architecture

How the home finance agent is built, and why. Each section below ends in a page that holds its
details. The contract every card agent offers is in [a2a-contract.md](a2a-contract.md); how each
part is tested is in [testing.md](testing.md).

## Sign-in

People sign in with their Google account; there is no other way in. The React page in the
browser keeps the person's Google ID token in a cookie that the FastAPI backend verifies on
every request; inside the backend, the token reaches the card-agent call through a context
variable, never through the graph state, so no checkpoint holds it. [sign-in.md](sign-in.md)

## Reviews

[The README](../README.md#how-a-review-runs) walks a review as the person sees it, from the start to
the report. [architecture/reviews.md](architecture/reviews.md) is what runs underneath: the graph,
the runner around it and the HTTP API the page calls.

## Events and the live stream

Every step of a review is an event appended to a per-review log in Postgres before it is
published, so a subscriber never sees what the log does not hold. The page is a server-sent event
stream that replays the log and then follows it live, and renders questions, totals and the report
from the latest events alone. [architecture/events.md](architecture/events.md)

## Scaling

The Docker stack runs several replicas of the backend behind an nginx edge, all on one Postgres and
one Redis, and any replica can serve any request. Two concerns follow, each a GitHub label beside
`scalability`: **scaling safety**, that it is safe to run more than one replica without errors; and
**scaling out**, that adding replicas serves more households without degrading anyone's experience.
[architecture/scaling.md](architecture/scaling.md)

## Storage

One Postgres database holds the reviews, their event logs, the person's merchant memory, their
report memory and LangGraph's checkpoints, all created by the migration run. Merchant memory
outlives a review; report memory lets a repeated prompt cost no model call.
[architecture/storage.md](architecture/storage.md)

## Configuration

The environment and `backend/.env` carry this agent's own settings; the card agents live in
`backend/card-agents.yaml`, written by the scripts, and the budget in `config/budget.yaml`. A
missing or malformed required setting stops startup rather than defaulting.
[architecture/configuration.md](architecture/configuration.md)

## Codebase structure

One package, `hfm`, in five layers with imports pointing inwards only, enforced by import-linter.
[architecture/codebase-structure.md](architecture/codebase-structure.md)
