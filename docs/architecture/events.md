# Events and the live stream

Every step of a review is an event, and the React page in the browser renders the review from
those events alone. Because the events are stored, a reload, a link opened later or a second device
replays them and shows the review exactly where it stands.

## The log comes first

The review's event log in Postgres is the source of truth for what the page shows. Each event is
appended to it, which gives it the next sequence number, and only then published to live
subscribers, so nobody ever sees an event the log does not hold. Each event is also stamped with the
time it was logged, so a replayed event shows when it happened.

| Event | Carries |
|---|---|
| `agent.discovered` | A card agent that passed discovery. |
| `agent.status` | A card agent's task state and progress text. |
| `transactions.batch` | A batch of rows from one card agent, each with its category and confidence. |
| `review.question` | The open questions: merchants to categorize, card agents waiting for the person. |
| `review.totals` | Spend and limit per category, standing-order spend, skipped agents, and each row's counted category. |
| `review.writing` | The model is writing the summary, which can take a while. |
| `review.report` | The summary. |
| `review.status` | The review's new status: `running`, `waiting` or `completed`. |
| `review.failed` | The failure message; the review is now `failed`. |

## The stream

`GET /api/reviews/{id}/events` is a server-sent event stream. It subscribes to the review's live
channel first, then replays the log, then follows live events, dropping any the replay already
covered by its sequence number. Each frame's id is that sequence number, so a reconnecting browser
gets only what followed. A comment line keeps a quiet stream inside the edge's read timeout, and
the stream ends when the browser leaves or the server shuts down.

Live delivery crosses replicas through Redis publish and subscribe, so the replica that runs a
review and the replica that serves the browser need not be the same. Redis keeps nothing; the log
does, and a browser that reconnects replays from it everything it has not seen. Without Redis, as in
`start.sh --host`, one process runs every review and serves every stream.

## The page

Questions, the spending pie and the report come from the latest question, totals and report
events, and the review's status from the latest status or failure event. The picked month lives in
the page's URL, so a month with a standing review replays that review's log on any reload.

Around that, the page lets the person work with a finished review:

- **Raw transactions** are folded above the totals and unfold when a doubtful row arrives. Each row
  shows the card agent's confidence, marked "overruled" once the person chose the category.
- **Recategorizing** a merchant on a completed review applies to every row of that merchant and
  reruns the totals and the report.
- **Choosing a slice** of the pie, or the standing-order spend, lists just those rows.
- **"Include expected charges"** adds the standing orders and installments an earlier month says
  are still to come, marked as expected, and dims the report, which narrates charged rows only. It
  starts ticked on a review that skipped a card agent, whose recurring charges would otherwise be
  missing.

The page shows whole amounts; the server keeps them exact.
