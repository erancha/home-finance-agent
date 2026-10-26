# Scaling

The Docker stack runs the backend as several replicas, the count set by `deploy: replicas` in
compose, behind an nginx edge, all on one Postgres and one Redis.

## Scaling safety

Several replicas of the backend must behave exactly as one would: a replica may start or stop,
requests may land on any replica in any order, and the person must see the same result as from a
single process. In particular, a replica must be redeployable while a review runs, with that review
completing; two answers sent at once for one review must resume it once, and two review starts sent
at once must both count toward the number of reviews a person may start in 24 hours
(`DAILY_REVIEW_LIMIT`, [reviews.md](reviews.md)); and an answer must be held until the run settles
whichever replica receives it.

What a review needs therefore crosses processes: every event is appended to Postgres before it is
published and a stream replays the log by sequence number ([events.md](events.md)); sign-in is a
cookie verified on every request; live events travel through Redis; and a paused review belongs to
no process, so whichever replica receives the answer resumes it from the checkpoint. What is still
open under this term is tracked in this repo's GitHub issues: the `scalability` label with the
`scaling-safety` label.

## Scaling out

Scaling out, as this page and the `scaling-out` label use the term, is scalability in the classic
sense: the stack serves more households by adding replicas, and a household's experience, the time
from a start to the first question and to the report, stays what it is under a light load. The load
is not even. Most cards' statements close in the first days of a month, so many households start
their review in the same few days, and that surge must be absorbed rather than refused: a start that
cannot run at once must wait briefly, survive a restart and run in turn, and the only limit a person
meets must be `DAILY_REVIEW_LIMIT`. What is still open under this term is tracked in this repo's
GitHub issues: the `scalability` label with the `scaling-out` label.

## The edge service

An nginx service, `edge` (`nginx/default.conf`), is the only one that publishes port 8010, and it
spreads requests over the replicas. It looks up the replicas' addresses again every 5 seconds, so a
replica added by scaling or recreated by a redeploy starts receiving requests without an edge
restart. Its access log names the replica that served each request (`docker-helper.sh --logs
edge`). `start.sh --host` has no edge: uvicorn serves the port itself.
