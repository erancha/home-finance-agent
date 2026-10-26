# Events and the live stream

Every step of a review is an event. `application/event_sink.py` appends it to the review's event
log in Postgres first, which assigns the next per-review sequence number, and then publishes it to
live subscribers, so a subscriber never sees an event the log does not hold. It also stamps the
event's data with `at`, the UTC time it was logged, so a replayed event shows when it happened;
the page's progress list prefixes each message with that time in local `YYYY/MM/DD HH:MM:SS`. An
input request's text is shown there in red, and the question below it offers only the action: the
agent's page, as a button, and continue.

| Event | Data |
|---|---|
| `agent.discovered` | `agent`, `url`, `streaming` |
| `agent.status` | `agent`, `state` (a `TASK_STATE_*` name), `text` |
| `transactions.batch` | `agent`, `month`, `count`, `transactions`, each row with its `merchantKey`; rows may repeat after a "continue", and the page shows each (agent, id) once; a row's `confidence` is the card agent's, `high`, `medium` or `low` |
| `review.question` | `questions`: each with `id`, `kind` (`categorize` with `merchant`, `transactions` (every row of the merchant), `options`, or `remote-input` with `agent`, `text`, `link` (null when the agent names no page), `actions`) |
| `review.totals` | `currency`, `totals` (`category`, `spent`, `limit`, `over`), `standingOrders` (the spend charged by standing order, across categories), `skipped`, `categories` (agent to row id to the category the totals counted), `chosen` (agent to the ids of rows whose category the person chose), `options` (the categories a person may assign) |
| `review.writing` | nothing beyond `at`: the model is being asked for the summary, which can take a while. |
| `review.report` | `text` |
| `review.failed` | `message`; the review is now `failed` |
| `review.status` | `status`: the review's new status, `running`, `waiting` or `completed` |

`GET /api/reviews/{id}/events` is a server-sent event stream (`platform/api/events.py`). It
subscribes to the review's live channel first, then replays the log, then sends live events; a live
event the replay already covered is dropped by its sequence number. Each frame's `id` is the
sequence number, so a reconnecting browser sends `Last-Event-ID` and gets only what followed. A
comment line goes out every 15 seconds on a quiet stream, inside the nginx edge's default
60-second read timeout; the response carries `X-Accel-Buffering: no`, so the edge passes each frame
through unbuffered. The stream stays open after the review ends and closes when the browser leaves
or the server shuts down: `signal_shutdown` in `platform/app.py` catches SIGINT and SIGTERM and
ends open streams, since uvicorn waits for open responses before it runs the shutdown code.

Live delivery is an event bus behind the `EventBus` port. With `REDIS_URL` set, the bus is Redis
publish/subscribe (`adapters/redis_bus.py`): a replica publishes each event on the review's channel
after appending it to the log, and a stream served by any replica subscribes to that channel, so the
progress list is complete whichever replica runs the review and whichever serves the browser. The
subscription is confirmed by Redis before the route replays the log, so no event falls between the
two. Unset, the bus is in-process (`adapters/memory_bus.py`), and the one process serves every
stream of the reviews it runs.

**The page renders from the stream.** Questions, the spending pie and the report come from the
latest `review.question`, `review.totals` and `review.report` events, each sequence number kept
once. Whether the review is running, waiting for answers or completed comes from the latest
`review.status` or `review.failed` event; until the log holds one, the page uses the status in the
month's view. The page puts the picked month in its URL (`?month=YYYY-MM`) and reads the month's
view (`GET /api/months/{month}`) whenever the month changes and after a start or a clear; a month
with a standing review replays that review's log, so a reload or a link opened later shows it where
it stands, open question included. The raw transactions, folded above the totals, unfold once when a
`low`-confidence row arrives while the review is in progress (not when a finished review is
reopened); they show each row's merchant, with the statement text as its tooltip when they differ,
the card agent's confidence ("AI confidence": red below `high`, on yellow when `low`, marked
"overruled" and plain once the person chose the category, which `review.totals` lists under
`chosen`), its details (installment, foreign amount, abroad, standing order) and the category the
latest totals counted for it; once the review is completed, a category can be changed there, for
every row of that merchant, and is sent to `/categories`. Choosing a category's slice or legend
entry in the totals lists only the raw transactions counted under it; the Totals heading lists all
again. Below the legend, the standing-order spend lists only the standing orders when chosen, and a
box in the raw transactions turns that filter on and off. On a completed review, "Include expected
charges" adds the rows `/expected` projects to the raw transactions (listed first and unfolded,
marked "expected", never recategorized), the pie, its legend and the standing-order spend, and dims
the report, which narrates the charged rows only. The box starts ticked on a review that skipped a
card agent, whose recurring charges would otherwise be missing. The answer is fetched on the first
tick and kept in the page while the box is toggled; new totals, as after a recategorize, make it
stale, so it is fetched again. Nothing about it is stored. The page shows amounts in whole units
with thousands separators; the server keeps them exact. A frame the page cannot parse is logged and
shown as a stream error.
