# A2A contract: the `monthly-transactions` skill

This page is the contract every card agent offers the home finance agent, and the source of truth
for it: a card agent that meets it is connected with `add-card-agent.sh` and no code change here.
The home finance agent's client, `backend/src/hfm/adapters/a2a_client.py`, enforces each point
below, so a change on either side is checked against this list. amex-agent, the demo's card
agent, documents how it implements the contract in its own repo
([amex-agent/docs/a2a-contract.md](https://github.com/erancha/amex-agent/blob/main/docs/a2a-contract.md)).

**Contents:** [Transport](#transport) · [Agent card](#agent-card) · [Request](#request) ·
[Stream events](#stream-events) · [Transaction rows](#transaction-rows) ·
[Taxonomy](#taxonomy) · [Input required and continue](#input-required-and-continue) ·
[Authentication](#authentication) · [Failures](#failures)

## Transport

- A2A protocol `1.0` over the JSON-RPC binding. The home finance agent speaks it through the
  Python `a2a-sdk` 1.x, which sends the required `A2A-Version: 1.0` header on every call.
- Streaming only: every request is `SendStreamingMessage`, and a card agent need not support the
  blocking `SendMessage`. The home finance agent never calls it, because a server built on the
  a2a-java SDK can answer it with a timeout error for a task that did finish.
- Task states are read by their wire names: `TASK_STATE_SUBMITTED`, `TASK_STATE_WORKING`,
  `TASK_STATE_INPUT_REQUIRED`, `TASK_STATE_AUTH_REQUIRED`, `TASK_STATE_COMPLETED`,
  `TASK_STATE_CANCELED`, `TASK_STATE_FAILED`, plus `TASK_STATE_REJECTED`, which the client treats
  as a failure. The client keys on the state, never on a `final` flag.
- Every data part travels as a protobuf `Struct`: an object's key order is not preserved and every
  number is a JSON double. The client reads fields by name and parses numbers as numbers.

## Agent card

Read from `/.well-known/agent-card.json` at the agent's registered URL, without credentials. The
client requires:

- a skill with id `monthly-transactions`;
- a `supportedInterfaces` entry with `protocolBinding` `JSONRPC` and a `url`. The client calls that
  URL, not the one it fetched the card from, so the advertised URL must be reachable from the home
  finance agent (the end-to-end compose file sets it to the agent's service address);
- in `securitySchemes`, an `openIdConnectSecurityScheme` (the person's token) and an
  `apiKeySecurityScheme` with `location` `header` (the caller secret), and one entry of
  `securityRequirements` naming both; the secret is sent under that API key scheme's `name`. A
  card agent that declares the schemes only while it requires credentials must run with them
  required.

A card that fails any of these, or cannot be fetched, fails the review with `review.failed`
naming the agent. `capabilities.streaming` is reported in `agent.discovered`.

## Request

A user message with one data part:

```json
{"month": "2026-10"}
```

`month` is the **billing month**, `YYYY-MM`: the month the card is charged, as printed on the
statement. A month in any other shape is the card agent's to reject, never to read as a nearby
month.

## Stream events

A covered month produces, on one stream, status updates and then the rows:

- A status update (or a task snapshot's status) becomes `agent.status` with the state name and the
  status message's text, shown live on the page.
- Each artifact data part is one batch of up to 25 rows, in the shape under
  [Transaction rows](#transaction-rows); all batches of a task share one `artifactId`. A snapshot's
  artifacts count like streamed ones. A statement with no rows still sends one batch with an empty
  `transactions` list.
- `TASK_STATE_COMPLETED` ends the fetch.
- `TASK_STATE_INPUT_REQUIRED` and `TASK_STATE_AUTH_REQUIRED` are interrupted states: the task
  stays alive, the update is not flagged `final`, and the agent closes the stream right after it;
  the client treats that close as the normal end of the fetch.
- A stream that ends in any other state, or a bare message instead of a task, fails the fetch. A
  stream response with no task, update or message makes the agent unusable.

## Transaction rows

Each artifact data part:

```json
{
  "month": "2026-10",
  "currency": "ILS",
  "transactions": [
    {
      "id": "20261002-09",
      "transactionDate": "2026-09-04",
      "chargeDate": "2026-10-02",
      "merchant": "Cellcom",
      "rawMerchant": "סלקום ישראל בע\"מ",
      "amount": 46.21,
      "originalAmount": null,
      "originalCurrency": null,
      "standingOrder": true,
      "abroad": false,
      "installment": null,
      "category": "utilities",
      "confidence": "high"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `month` | Billing month of the statement, `YYYY-MM`. |
| `currency` | Card currency, `ILS`. Not read by the client: amounts are summed as shekels. |
| `id` | Stable across runs of the same month, so the review counts each (agent, `id`) once and rows resent after a "continue" do not double the totals. |
| `transactionDate` | Purchase date, `YYYY-MM-DD`; usually in the month before the billing month. |
| `chargeDate` | Date the card is charged, `YYYY-MM-DD`. |
| `merchant` | Readable display name; the raw string when the agent has none. |
| `rawMerchant` | The merchant string exactly as the statement prints it. |
| `amount` | Charged amount in the card currency. |
| `originalAmount`, `originalCurrency` | Purchase amount and ISO currency code, set only when the purchase currency differs from the card currency; otherwise `null`. |
| `standingOrder` | The statement marks the row as a standing order. |
| `abroad` | The statement lists the purchase as made abroad. |
| `installment` | `{"number": 3, "total": 10}` for installment 3 of 10, otherwise `null`. |
| `category` | One value of the [taxonomy](#taxonomy). |
| `confidence` | How sure the agent is of `category`: `high`, `medium` or `low`. |

The client reads every field of every row; a missing field, a category outside the taxonomy or
a confidence outside the three values fails the fetch. Amounts become `Decimal` through their
shortest text form and installment numbers become integers. Rows with `low` confidence or category
`uncategorized` become questions for the person; unanswered, they keep the agent's category, so a
`low` row should carry the agent's best guess.

## Taxonomy

Fixed, shared by every card agent, and listed in each agent's skill description:

`groceries`, `dining`, `transport`, `utilities`, `housing`, `health`, `insurance`, `education`,
`shopping`, `entertainment`, `travel`, `gifts`, `other`, `uncategorized`.

The home finance agent's copy is `backend/src/hfm/domain/taxonomy.py`; a value outside it fails
the fetch.

## Input required and continue

When the agent has no statement for the month, the task enters `TASK_STATE_INPUT_REQUIRED` with a
status message of two parts: a text part for the human, shown as the question, and a data part

```json
{"reason": "statement-missing", "month": "2026-09", "page": "/statements.html",
 "user": "<account id>"}
```

- `reason`: `statement-missing`.
- `month`: the billing month, `YYYY-MM`, that no statement covers.
- `page`: optional. The path, on the agent's own origin, of a page where a person loads the
  missing statement; an agent with no such page omits it. The question links to that path on the
  agent's browser address (`browser_url` in `backend/card-agents.yaml`) and offers only
  "continue". A `page` that is not a path on the agent's own origin (a string starting with a
  single `/`) is refused.
- `user`: the person the task belongs to, the agent's own bookkeeping; not read here.

A missing text part, any number of data parts other than one, or a data part without `reason` or
`month` fails the review with `agent '<name>' is unusable: asked for input ...` naming the fault.

When the agent cannot verify the forwarded token (missing, expired, issued to another client, or
a continue from a different Google account than the task's), the task enters
`TASK_STATE_AUTH_REQUIRED` with the same two parts, the data part's `reason` being
`sign-in-required`. The client parses it like a statement request; any other reason in that state
fails the review with `asked for sign-in with reason ...`. The question offers only "continue" and
no link: the page shows the Google button inline, and the continue carries the fresh token.

To continue, the client sends a new message on the same `taskId` and `contextId`, with the
person's current token and the caller secret as on every call, and one data part:

```json
{"action": "continue"}
```

The agent then either completes the month or asks again, on a stream shaped as above. The home
finance agent never cancels a task; "skip", offered only when the agent names no page, simply
stops asking that agent, leaving its task waiting on the agent side.

## Authentication

Every call carries two credentials, chosen per call because one client serves every person's
reviews:

- the caller secret, the `shared_secret` of the agent's registry entry, under the header the
  agent card names (`X-Caller-Secret` for amex-agent). It proves which registered caller is
  asking. The card and the health endpoint are open; anything else with a wrong or missing secret
  gets HTTP 401;
- `Authorization: Bearer <the signed-in person's Google ID token>`, forwarded as the page sent it.
  It says which person the call is for; the agent verifies it itself against Google's published
  keys, with the audience equal to the caller's registered client id. A token the agent cannot
  verify is answered inside the task with `TASK_STATE_AUTH_REQUIRED`, never with an HTTP error,
  so the same task continues once the person signs in again.

How the two credentials are registered and handed over is in
[connecting-agents.md](connecting-agents.md); the design is in [sign-in.md](sign-in.md).

## Failures

| Agent side | Home finance agent side |
|---|---|
| `TASK_STATE_FAILED`, `TASK_STATE_CANCELED`, `TASK_STATE_REJECTED` | The fetch fails with the status text, or the state name without one. |
| A JSON-RPC error frame on the stream | The fetch fails with the SDK's message. |
| HTTP 401 on the call | `<agent> refused this agent's secret; check its registration`. |
| A refused or dropped connection, or a timeout, on the card or the call | `<agent> could not be reached at <url>; it may not be running`. |
| Any other HTTP or JSON-RPC error | The SDK's message. |
| An unusable card or a garbled stream | `<agent> <what is wrong>`, e.g. `amex advertises no JSON-RPC interface`. |

Either way the review fails, and `review.failed` carries the message, read on the page as
`Review failed: <message>`; a failed fetch reads `<agent> <message>`. The SDK's error is logged at
warning with the agent's name.
