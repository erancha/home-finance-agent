# Reviews

How one review runs underneath the React page in the browser: a LangGraph graph does the work, a
runner around it owns the review's status, its limits and the person's answers, and an HTTP API lets
the page drive both.
The event stream the page renders from is in [events.md](events.md).

## The graph

The review is a LangGraph state machine whose state is saved to Postgres after every step. The
review id is also the graph's thread id, so one id names both the review row and its saved state.

```mermaid
flowchart TD
  S([start]) --> D[discover]
  S -->|completed review rerun with categories| C[recategorize]
  C --> Rep
  D -->|one Send per agent| F[fetch_agent]
  F --> R[reconcile]
  R --> P[pose]
  P --> A[ask]
  A -.->|interrupt: wait for answers| H((you))
  H -.->|resume with answers| A
  A -->|one Send per agent answered continue| F
  A -->|nobody to fetch again| Rep[report]
  Rep --> E([end])
```

| Step | Does |
|---|---|
| `discover` | Reads each connected card agent's Agent Card and checks it offers the contract; an unusable agent fails the review. |
| `fetch_agent` | Streams one agent's month, or continues its paused task, and collects the rows and any request for the person. |
| `reconcile` | Applies the person's merchant memory over the card agents' categories and computes the totals. |
| `pose` | Turns uncertain merchants and paused card agents into questions. |
| `ask` | Pauses until the answers arrive, then remembers the chosen categories. |
| `recategorize` | Applies categories chosen on a finished review, without fetching again. |
| `report` | Has the model narrate the totals, or reuses the text it wrote for the same totals before. |

Two loops run through the graph. The human loop pauses at `ask` for as long as it takes. The fetch
loop returns to `fetch_agent` for every card agent whose question was answered "continue", and the
new rows go through `reconcile`, `pose` and `ask` again.

**Why the design looks like this:**

- **The number of fetches is data, not graph shape.** There is one fetch per connected card agent at
  the start, then one per agent answered "continue". LangGraph's `Send` runs exactly those fetches
  in parallel, and each shared state key has a merge rule, so a row resent after a "continue" is
  counted once.
- **A paused review holds no process.** It is a saved state in Postgres, so the answer may come
  hours later, after a restart, or to another replica.
- **Asking is split from posing.** On resume LangGraph reruns the interrupted step from its first
  line. `pose` emits and saves the questions, and `ask` only reads them and pauses, so a resume
  never emits a question twice.
- **The checkpoint holds no secret.** The state names card agents only; each fetch looks up the
  agent's URL and secret when it runs, and the person's token reaches the call outside the state
  ([sign-in.md](../sign-in.md)). A paused review whose card agent has since been disconnected fails
  naming it when it resumes.
- **Checkpointed types are an allow-list.** LangGraph rebuilds only the domain types the review
  declares, in strict mode, and the tests fail on any checkpoint warning.
- **Numbers never come from the model.** Totals, limits and overruns are computed in code with
  exact decimals; the model receives them as a table and returns prose that is shown as is.

**A card agent's task state drives the fetch,** never the stream's final flag. Working states are
shown as progress. Input required becomes a question for the person, most often a statement not
loaded yet, with a link to the card agent's page. Auth required becomes a "sign in again and
continue" question. Completed ends the fetch, and failed, canceled or rejected fails the review with
the card agent's text. The full contract is in [a2a-contract.md](../a2a-contract.md).

**"Continue" and "skip".** "Continue" resumes the same A2A task on the card agent, which either
completes the month or asks again. "Skip" leaves that card agent out: the review totals what it has
and the report says plainly that the agent's spend is missing. A mid-month review needs skip, since
the month's statement does not exist yet, and "Include expected charges" then fills in the skipped
agent's recurring charges from an earlier month.

## The runner

The runner owns every graph invocation, each on behalf of the signed-in person, and runs it in the
background, so the request that starts or answers a review returns at once. A review has at most
one invocation in flight, and a review that belongs to someone else answers exactly like one that
does not exist.

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

## HTTP API

| Route | Purpose |
|---|---|
| `POST /api/reviews` | Start a review of a month; refused when the month has a standing review or the day's starts are used. |
| `GET /api/reviews/{id}` | The review's month, status, open questions, totals and report. |
| `GET /api/months/{month}` | The month's standing review, if any, and whether a start is allowed now. |
| `DELETE /api/reviews/{id}` | Clear a review that is not running, freeing its month. |
| `POST /api/reviews/{id}/answers` | Answer a waiting review's questions. |
| `POST /api/reviews/{id}/categories` | Choose categories for merchants of a completed review, which reruns its totals and report. |
| `GET /api/reviews/{id}/expected` | The charges a completed review's month still expects, projected from an earlier month. |
| `GET /api/reviews/{id}/events` | The live event stream ([events.md](events.md)). |
| `GET /health`, `GET /ready` | The process is up; and the database answers. |

Money travels as a decimal string with two places, and totals are computed on exact values before
it is formatted. The page and the report prompt both show whole amounts with thousands separators.
