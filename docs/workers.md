# Workers' responsibilities and flows

This document details the work no request waits on, behind the parts that
[Architecture](architecture.md#the-parts) summarizes: the review runs that `ReviewRunner` starts
in every `manager` replica, and the one-shot schema migration. The routes that start, answer or
rerun a review are in [API endpoints](api.md); the graph a run walks is in
[Reviews](architecture/reviews.md).

## `ReviewRunner` runs

The runner, `ReviewRunner` in `platform/review_runner.py`, owns every graph invocation, each on
behalf of the signed-in person, and runs it in the background, so the request that starts or
answers a review returns at once. A review has at most one invocation in flight, and a review that
belongs to someone else answers exactly like one that does not exist.

| Status | Means |
|---|---|
| `running` | An invocation is in flight. |
| `waiting` | The graph paused for answers. |
| `completed` | The graph reached its end; choosing new categories runs it again. |
| `failed` | The invocation raised, and the message is shown to the person. |

**Every status change is also an event,** written in the same transaction, and `waiting` and
`completed` only after the last checkpoint. The page takes the status from these events, so by the
time it shows a question, every replica already sees the review as waiting.

**A restart keeps waiting reviews and fails the running ones it stopped.** A waiting review is
only saved state. A running review is held by a lock in Postgres that every replica sees, taken
before its status becomes running and released once its run records the outcome. Postgres also
releases it when the replica's connection dies, so a running review whose lock no one holds lost
its run. The next replica to start marks such a review failed, with a message asking the person to
clear it and start again, and leaves alone a review another replica is running.

**Every status change names the status it changes from.** The change is checked and written in
one transaction, so of two answers reaching two replicas at once, one resumes the review and the
other is refused. A request finds the review's lock held while a run is in flight, and is refused
too. A person's starts are counted one at a time under a lock of their own, so two starts at once
cannot pass the daily limit together.

**Answers are checked before the graph resumes.** Every card agent's question must be answered,
with one of the offered options, and merchant questions may be left unanswered. A bad set is
refused with the offending ids and the review stays paused. The check lives in the runner because
LangGraph replays a failed resume value on every later resume, so one bad answer set would break
the review for good.

**An answer that races the pause is held.** The question event goes out just before the pause is
saved, so a fast answer waits briefly for the run to settle instead of being refused.

**Starts are rationed,** because every start costs model calls on the card agents' side and
usually on this one. A month holds one standing review per person until they clear it, and a
person may start a limited number of reviews per day, cleared ones included. A unique index holds
the one-standing-review rule in the database as well, whichever replica receives the start.

**Failures are readable.** A review error, such as an unreachable card agent or its failed task,
reaches the person verbatim. Anything else is shown as its type with "see the server log" and is
logged in full.

## `migrate`

The Compose service `migrate` is a one-shot run of `alembic upgrade head` from the manager image,
after `db` is healthy; the manager replicas start once it has completed. The run creates and
migrates this agent's tables and LangGraph's checkpoint tables
([Data model](data-model.md#langgraphs-checkpoints)).
