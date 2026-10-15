# A2A contract: what the home finance agent relies on

amex-agent's repo holds the source of truth:
[amex-agent/docs/a2a-contract.md](../../../java/amex-agent/docs/a2a-contract.md) (relative to a
checkout beside this one; on GitHub:
[erancha/amex-agent](https://github.com/erancha/amex-agent/blob/main/docs/a2a-contract.md)). This
page lists only the parts of it the home finance agent's client,
`backend/src/hfm/adapters/a2a_client.py`, depends on, so a change on the agent side can be checked
against this list.

**Contents:** [Transport](#transport) · [Agent card](#agent-card) · [Request](#request) ·
[Stream events](#stream-events) · [Transaction rows](#transaction-rows) ·
[Input required and continue](#input-required-and-continue) · [Failures](#failures)

## Transport

- A2A protocol `1.0` over JSON-RPC, through the Python `a2a-sdk` 1.x, which sends the required
  `A2A-Version: 1.0` header on every call.
- Streaming only: every request is `SendStreamingMessage`. The blocking `SendMessage` is never
  used: the a2a-java SDK can answer it with a timeout error for a task that did finish.
- `Authorization: Bearer <AMEX_AGENT_TOKEN>` on every request. The agent's card and health endpoint
  are open; anything else with a wrong or missing token gets HTTP 401.
- Task states are read by their wire names: `TASK_STATE_SUBMITTED`, `TASK_STATE_WORKING`,
  `TASK_STATE_INPUT_REQUIRED`, `TASK_STATE_COMPLETED`, `TASK_STATE_CANCELED`,
  `TASK_STATE_FAILED`, plus `TASK_STATE_REJECTED`, which the client treats as a failure.

## Agent card

Read from `/.well-known/agent-card.json` at the agent's configured URL
(`http://localhost:8020/.well-known/agent-card.json` by default). The client requires:

- a skill with id `monthly-transactions`;
- a `supportedInterfaces` entry with `protocolBinding` `JSONRPC` and a `url`. The client calls that
  URL, not the one it fetched the card from, so the agent's `APP_AGENT_URL` must be reachable from
  the home finance agent (compose sets it to `http://amex-agent:8020`);
- an HTTP `bearer` scheme in `securitySchemes`, and a bearer token configured for the agent. The
  card agent declares the scheme only while it requires the token (`APP_A2A_AUTH_REQUIRED=true`,
  its default), so the home finance agent needs the agent to run with auth on.

A card that fails any of these, or cannot be fetched, fails the review with `review.failed`
naming the agent. `capabilities.streaming` is reported in `agent.discovered`.

## Request

A user message with one data part:

```json
{"month": "2026-10"}
```

`month` is the billing month, `YYYY-MM`.

## Stream events

The client keys on the task state, never on a `final` flag:

- A status update (or a task snapshot's status) becomes `agent.status` with the state name and the
  status message's text.
- Each artifact data part is one batch of up to 25 rows; all batches of a task share one
  `artifactId`. A snapshot's artifacts count like streamed ones.
- `TASK_STATE_COMPLETED` ends the fetch.
- `TASK_STATE_INPUT_REQUIRED` is not flagged `final`, and the agent closes the stream right after
  it; the client treats that close as the normal end of the fetch.
- A stream that ends in any other state, or a bare message instead of a task, fails the fetch. A
  stream response with no task, update or message makes the agent unusable.

## Transaction rows

The client reads `month` and `transactions` from each data part, and every field of each row:
`id`, `transactionDate`, `chargeDate`, `merchant`, `rawMerchant`, `amount`, `originalAmount`,
`originalCurrency`, `standingOrder`, `abroad`, `installment` (`number`, `total`), `category`,
`confidence`. A missing field or a category outside the shared taxonomy fails the fetch.

- `id` is the statement's voucher number; the review counts each (agent, `id`) once, so rows
  resent after a "continue" do not double the totals.
- Numbers arrive as JSON doubles (`86.9`, installment `3.0`); amounts become `Decimal` through
  their shortest text form, installment numbers become integers.
- `confidence` is `high`, `medium` or `low`; any other value fails the fetch. Rows with `low`
  confidence or category `uncategorized` become questions for the user; unanswered, they keep the
  agent's category.

Under its `e2e` profile, which the end-to-end test runs, amex-agent categorizes by a keyword table:
its test statement for 2026-10 then has 24 rows and leaves only `וים קלאבס בע"מ - הו"`
uncategorized, every other row `high`, so that review always asks one question.

## Input required and continue

When the agent has no statement for the month, the task enters `TASK_STATE_INPUT_REQUIRED` with a
status message of two parts: a text part for the human, shown as the question, and a data part
`{"reason": "statement-missing", "month": "YYYY-MM", "page": "/statements.html"}`. `page` is
optional: the path, on the agent's own origin, of a page where a person loads the missing
statement; an agent with no such page omits it. The question links to that path on the agent's
browser address (`browser_url_env` in `config/agents.yaml`) and offers only "continue". A missing
text part, any number of data parts other than one, a data part without `reason` or `month`, or a
`page` that is not a path on the agent's own origin (a string starting with a single `/`) fails
the review with `agent '<name>' is unusable: asked for input ...` naming the fault.

To continue, the client sends a new message on the same `taskId` and `contextId` with one data
part:

```json
{"action": "continue"}
```

The agent rescans its statements folder and either completes the month or asks again. The home
finance agent never cancels a task; "skip", offered only when the agent names no page, simply
stops asking that agent, leaving its task waiting on the agent side.

## Failures

| Agent side | Home finance agent side |
|---|---|
| `TASK_STATE_FAILED`, `TASK_STATE_CANCELED`, `TASK_STATE_REJECTED` | The fetch fails with the status text, or the state name without one. |
| A JSON-RPC error frame, an HTTP error (`HTTP Error 401` for a wrong token) or a broken connection | The SDK raises it; the fetch fails with its message. |
| Card unreachable or unusable, or a garbled stream | `agent '<name>' is unusable: <reason>`. |

Either way the review fails, and `review.failed` carries the message; a failed fetch reads
`<agent>: <message>`.
`./scripts/start.sh` refuses to launch while `AMEX_AGENT_TOKEN` differs from the agent's
`APP_A2A_TOKEN`, so a token mismatch is caught before any review.
