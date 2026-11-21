# Scaling

This document details the scaling concerns that [Architecture](../architecture.md#scaling)
summarizes. The Docker stack runs the backend as several replicas behind an nginx edge, all on one
Postgres and one Redis. Two concerns follow: **scaling safety**, that it is safe to run more than
one replica without errors, and **scaling out**, that adding replicas serves more households
without degrading anyone's experience.

## Scaling safety

Several replicas of the backend behave as one would: a replica may start or stop, requests may
land on any replica in any order, and the person sees the same result as from a single process. In
particular, a replica can be redeployed while a review runs, and that review completes; two answers
sent at once for one review resume it once; and two review starts sent at once both count toward
the number of reviews a person may start in a day ([Workers](../workers.md#reviewrunner-runs)).

What a review needs therefore crosses processes: every event is appended to Postgres before it is
published and a stream replays the log by sequence number ([events.md](events.md)); sign-in is a
cookie verified on every request; live events travel through Redis; and a paused review belongs to
no process, so whichever replica receives the answer resumes it from the checkpoint.

## Scaling out

Scaling out, as this page uses the term, is scalability in the classic sense: the stack serves more
households by adding replicas, and a household's experience, the time from a start to the first
question and to the report, stays what it is under a light load. The load is not even. Most cards'
statements close in the first days of a month, so many households start their review in the same
few days. Every start runs at once, in the background of the replica that received it, so the
capacity to run reviews and the capacity to serve pages grow together, one replica at a time.
Nothing limits how many reviews run together beyond each person's daily and monthly start limits
([Workers](../workers.md#reviewrunner-runs)).

## The edge service

An nginx service, the edge, is the only one that publishes port 8010, and it spreads requests over
the replicas. It looks up the replicas' addresses again every 5 seconds, so a
replica added by scaling or recreated by a redeploy starts receiving requests without an edge
restart. Its access log names the replica that served each request (`docker-helper.sh --logs
edge`). An agent started on the host has no edge: uvicorn serves the port itself.
