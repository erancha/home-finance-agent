# Testing

What each layer of tests proves, and how to run it.

**Contents:** [Running](#running) · [Backend](#backend) · [Frontend](#frontend) ·
[End to end](#end-to-end) · [CI](#ci)

## Running

```bash
./scripts/test.sh                  # backend + frontend
./scripts/test.sh backend          # lint, types, import boundaries, pytest
./scripts/test.sh frontend         # typecheck, lint, component tests, production build
./scripts/test.sh frontend=unit    # typecheck and component tests only
./scripts/test.sh e2e              # a full review through both agents in Docker
```

The backend suite needs Docker running: its Postgres tests start a throwaway database. No test
needs an API key, and none reaches Google: tests sign their own tokens with a key pair generated at
import (`tests/auth_keys.py`) and verify them through the same code path with that public key.

## Backend

**Static gates**, in `scripts/test.sh backend`, each failing the run:

- `scripts/tests/test_load_env.sh`: `backend/.env` only fills variables the shell has not
  exported, a blank line included, a malformed line stops the load, the registry path is exported
  with its default, and a launch without the registry file is refused naming `init-env.sh`;
- `scripts/tests/test_init_env.sh`: `init-env.sh` creates `backend/.env` and an empty registry,
  creates a missing registry beside an existing env file without touching it, and rewrites the env
  file only with `--force`;
- `scripts/tests/test_add_card_agent.sh`: `add-card-agent.sh` writes an entry the registry loader
  reads, replaces an entry by name while keeping the others, starts from the empty registry
  `init-env.sh` writes, keeps the file owner-readable, and refuses blank options, values that are
  not plain scalars and a file it did not write, and writes the registry `CARD_AGENTS_FILE` names;
- `scripts/tests/test_sql_helper.sh`: `sql-helper.sh --rows` dumps 20 rows of each table unless
  `--limit` names another count, the count reaches the SQL as a psql variable, and a count that is
  not a whole number is refused naming the option;
- `ruff check src tests` (100-character lines);
- `mypy` over `src`;
- `lint-imports`: the four layer contracts of `backend/pyproject.toml` (see
  [architecture.md](architecture.md#layers)).

**pytest** then runs everything under `backend/tests`, laid out like `src`. `tests/fakes.py` holds
in-memory implementations of every port, and `tests/test_fakes.py` proves they satisfy their
ports and behave as the tests assume. `tests/conftest.py` sets `LANGGRAPH_STRICT_MSGPACK=true`,
unless the environment already sets it, before anything imports LangGraph.

| Layer | Proves |
|---|---|
| `domain/` | The taxonomy is the published list; values keep their identity when recategorized; events and questions render to JSON-safe shapes with the published event names; money text has two decimal places. |
| `application/test_reconcile.py` | Totals add up in `Decimal` and mark overruns; a remembered category overrides the agent's and counts as sure; uncategorized and `low`-confidence rows are grouped by merchant for questions; the same voucher arriving twice counts once (`test_transactions_reducer_dedupes_by_agent_and_id`); the standing-order spend sums only standing-order rows. |
| `application/test_questions.py` | Question ids and options; a request with a page links to it on the agent's browser address and offers only `continue`, so `skip` is refused; a `sign-in-required` request offers only `continue` and no link; categorize questions may go unanswered, while an answer set naming an unknown id or leaving out a remote question is rejected with the ids named (`test_validate_answers_rejects_a_missing_remote_answer_and_unknown_ids`), as are bad options and non-string values. |
| `application/test_report.py` | The prompt's table shows spent and limit as whole amounts with thousands separators, as the page does. |
| `domain/test_merchants.py` | Hebrew and English merchants lose company suffixes and trailing numbers; a key is never empty; a blank merchant is rejected. |
| `adapters/test_config_files.py` | The registry loads its entries in order; a missing file or `agents: []` means no card agents; a blank or missing field, a URL without an http(s) origin, a name listed twice, and entries that are not mappings are refused naming the entry; a budget category outside the taxonomy fails at load (`test_load_budget_rejects_unknown_category`); the shipped budget loads. |
| `adapters/test_a2a_client.py` | The A2A stream becomes port events: status, batches, input required with its task and optional page, auth required as a `sign-in-required` pause (any other reason in that state is refused), completed snapshots, resume ids, failed states, SDK errors, a stream that ends early; a malformed input request (a `page` that is not a path on the agent's origin included) or an empty stream response fails naming the agent and the fault. Each call carries the person's token as the bearer and the secret under the header the card names, and nothing on the HTTP client, which allows 300 s between stream events. A changed card on rediscovery gets a new SDK client. Cards without the skill (`test_discover_rejects_card_without_skill`), without a JSON-RPC interface, without the OpenID Connect or header API key scheme or a requirement joining them, or with no secret configured are refused. A refused connection at the card reads `<agent> could not be reached at <url>; it may not be running`, any other card fetch failure names the URL and the cause, HTTP 401 on the call reads `<agent> refused this agent's secret; check its registration`, and a dropped connection or timeout during the call reads as unreachable. Wire rows map field by field, and a numeric confidence is refused. |
| `adapters/test_google_tokens.py` | A valid token names the person and its expiry; email and name are optional; Google's bare issuer form is accepted for Google only; expired, wrong-audience, wrong-issuer, foreign-key, unsigned, symmetric and claim-less tokens are refused with a reason; a PEM file loads and a non-RSA key is refused; JWKS keys are picked by key id and fetched once. |
| `adapters/test_memory_bus.py` | A published event reaches only its channel's subscribers; a subscription ends with its context. |
| `adapters/test_redis_bus.py` | On a Testcontainers Redis, an event published by one bus reaches only its channel's subscribers on another, as across replicas; a subscription is live before its context body runs, which the event route counts on when it subscribes before replaying; a subscription ends with its context; the bus satisfies the port. |
| `adapters/test_report_writer.py` | The canned writer returns its text; the LangChain writer returns the model's reply; providers are built through LangChain with the key passed on; a GPT-5 model is asked for minimal reasoning and other OpenAI models for none; an unknown provider is named. |
| `adapters/test_a2a_client_live.py` | Skipped unless `LIVE_AGENT_URL`, `LIVE_AGENT_TOKEN` and `LIVE_AGENT_USER_TOKEN` point at a running agent and a person it accepts; then fetches 2026-10 from its test statement (24 rows). |
| `platform/test_config.py`, `test_logging.py`, `test_app.py` | Settings refuse a missing model, `LLM_MODEL=fake`, a model without `LLM_API_KEY` or a provider, and a missing `GOOGLE_CLIENT_ID`, while `HFM_E2E` needs no model, token verification defaults to Google, and the registry path has its default unless `CARD_AGENTS_FILE` is set, and `REDIS_URL` is optional and kept secret; logging levels, and successful `/health` and `/ready` access lines dropped to DEBUG; `/health`, `/ready`, the served page, live events staying in process unless `REDIS_URL` is set, the production wiring signing a person in with a token the configured public key verifies and recording a failed review in Postgres, and startup failing a review a stopped server left running. |

**Postgres and Redis.** `tests/conftest.py` starts `postgres:16` (and, for the Redis bus tests,
`redis:7-alpine`) with Testcontainers once per test module and applies the Alembic migrations.
`adapters/postgres/test_repositories.py` covers review rows, event sequences that never collide
under concurrent appends, reviews listed by status, a person's month holding one standing review
until it is cleared while another person reviews the same month independently, a person's reviews
created since a time listed cleared ones included, merchant memory upserts per person, report
memory answering a person's own text for each exact prompt, and a written report forgetting the
person's rows past the retention while another person's stay.
`platform/test_checkpointer.py` round-trips a checkpoint through Postgres with `Decimal` and domain
values intact, shows the default serializer losing a domain value that the allow-list keeps, and
reads a checkpoint back after every server connection was terminated, as a database restart does;
`platform/test_db.py` proves the same for the SQLAlchemy sessions. Both sever the connections
through `tests/platform/database_outage.py`. `platform/test_migrations.py` runs on a database
that saw only the migration run and finds the checkpoint tables at the library's latest version,
then drops the saver's version table and opens the checkpointer, which leaves it dropped: the
tables are the migration run's, so replicas booting together never create them.

**Graph.** `application/test_review_graph.py` runs the real graph on fakes and an in-memory
checkpointer with the review's serializer. It covers the happy path, a second review with the same
totals reusing the report without asking the model, the totals carrying the standing-order spend,
an unknown merchant pausing and being remembered, memory preventing the second question, a
remembered category outranking the agent's, "continue" refetching the same task, a
statement page linked on the agent's browser address, "skip" reporting partial data, two agents
where only the waiting one is refetched, rows resent on continue counted once, a review with no
agents, an unusable agent failing the review (`test_graph_fails_review_when_agent_unusable`), one of
two agents failing its task and a stream ending without a terminal event (each failing the review
naming the agent), a `low`-confidence guess asked about and kept when unanswered, an unanswered
merchant staying uncategorized and not asked again after a "continue", a completed review
recategorizing a merchant without refetching and rewriting the report, a missing remote answer
rejected on resume, a resume after the agent left the config failing with its name, and a full state
round trip through the serializer, a `sign-in-required` pause offering only continue and the
continue refetching, and a fetch outside a signed-in run raising rather than calling anonymously.
`test_no_checkpoint_or_pending_write_holds_an_agent_or_user_token` runs a review through a pause
and a "continue" and searches every stored checkpoint, metadata and pending-write blob for the
agent's secret and the person's token, while finding the person's id. A fixture fails any test that
makes LangGraph log a checkpoint warning, so a type missing from the allow-list cannot pass.

**Runner and API.** `platform/test_review_runner.py` drives `ReviewRunner`: waiting on the posed
question, a missing remote answer rejected with the graph still resumable, full answers completing
the review, recategorizing a completed review rerunning it to a second report while a review not
completed or an unknown merchant is refused, answers sent right after the question waiting for the
run to settle, a run that does not settle refused, domain failures and an agent's failed task shown
verbatim, infrastructure failures hidden and logged, `aclose` cancelling running reviews, and
`fail_interrupted` failing a review left running while a waiting one stays waiting. It also covers
the rations: a month with a standing review refused a second start naming it, a cleared review
hidden and its month started anew, a running review refused clearing, starts past the daily limit
refused with the time the next can start (cleared ones counted), and starts older than the window
ignored; and the month view naming the standing review, the starts left and when the next start is
allowed. Per person: another person's review is not found and their month is free, the daily limit
counts each person's own starts, and each fetch forwards the token of the request that started it.
`platform/api/test_agents.py` checks that the connected card agents are listed by name in registry
order, an empty registry lists none, and the route needs a session. `platform/api/test_auth.py`
checks sign-in: the client id is public, the posted credential becomes an HttpOnly, SameSite=Strict
cookie lasting as long as the token and Secure over https, a bad credential is 401 with the reason
and no cookie, every protected route is 401 without a valid cookie while `/health` stays open, and
sign-out drops the cookie. `platform/api/test_reviews.py` checks the HTTP codes (202, 404, 409, 422
with what is wrong, 204, 429 with `Retry-After`), recategorizing, clearing, the 409 naming the
standing review, the month route and another person's review being 404 included.
`platform/api/test_events.py` checks the stream: a page opened after the review paused still sees
the question through replay (`test_events_replays_persisted_events_before_tailing`), events racing
the replay arrive once each, an anonymous subscription is 401, and the stream ends soon after
shutdown. Two tests run real uvicorn on the main thread so its signal handlers are the production
ones: SIGTERM ends open streams so the shutdown code runs, and the shutdown handler chains to the
one installed before it. A third test, without uvicorn, installs a handler Python cannot see and
checks the shutdown handler restores the default action in its place.

**Repository rules.**

| Test | Guards |
|---|---|
| `test_architecture.py` | Runs `lint-imports` inside pytest. |
| `test_requirements_lock.py` | Every direct dependency is pinned exactly in `requirements.txt`, the lock was compiled on the Python the image runs (`scripts/lock.sh`), and both the Dockerfile and the test venv install under it. |
| `test_readme_toc.py` | Every README contents link reaches a heading. |
| `test_edge_config.py` | The nginx edge resolves the manager name through Docker's DNS while it runs, so scaled or recreated replicas take traffic without an edge restart, and its access log names the replica that served each request. |
| `test_docker_compose_ports.py` | Postgres is published on `127.0.0.1` only; only the nginx edge (8010) and, in the end-to-end file, amex-agent (8020) listen on every interface, and the home finance agent itself publishes no port. |
| `test_env_example.py` | `backend/.env.example` documents every settings key and nothing else beyond the named operational keys. |
| `test_docker_compose_replicas.py` | The development stack runs more than one replica of the agent sharing the `redis` service; the end-to-end file runs one. |

## Frontend

Vitest with Testing Library in jsdom (`frontend/src/**/*.test.ts[x]`); `src/test/fakeEventSource.ts`
stands in for the browser's `EventSource`.

| Test | Proves |
|---|---|
| `App.test.tsx` | A person the server knows sees the review page and their email; a stranger sees Google's button, whose credential is posted and signs them in with the month kept in the URL; a refused sign-in shows its reason; sign-out and any 401 drop back to the button; a server that cannot say who is signed in is reported, not mistaken for a stranger. `src/test/fakeGoogle.ts` stands in for Google's script. |
| `api/client.test.ts` | An error body becomes an `ApiException` with status and detail; a rejected answer set names its missing, unknown and invalid ids, a validation error lists its messages, and a record detail shows its message; a 401 is announced on window; 204 returns nothing; bodies are posted as JSON and DELETE is sent. |
| `hooks/useReviewEvents.test.ts` | Events accumulate in order with the last event id, each sequence number once; a malformed frame or one without a sequence number is logged, reported as a stream error and skipped; the stream closes on unmount and restarts clean for a new review. |
| `components/CollapsibleSection.test.tsx` | The heading toggles the body; a section asked to start folded opens on the first click. |
| `features/review/EventFeed.test.tsx` | Each message starts with its local time; a status without text shows the state alone; an input request's text is shown in red; the last line ends with a spinner while the review is working, and only then. |
| `features/review/TransactionsSection.test.tsx` | The raw transactions start folded under a heading that counts them, and unfold once when a `low`-confidence row arrives while the review is in progress, staying as the person left them afterwards and folded for a review that already ended; a row repeated across batches shows once; each row shows its details such as its installment, the AI confidence, marked when below high and plain with "(overruled)" once the person chose the category, the statement text as the merchant's tooltip, and the category the totals counted, read-only until the review completes; a category chosen on one row applies to every row of the merchant and is sent once, and kept when the server refuses it; a category chosen in the totals unfolds the section with only its rows; the standing-orders box lists only standing orders; nothing renders before the first row. |
| `format.test.ts` | Amounts round to whole units with thousands separators; times show as local `YYYY/MM/DD HH:MM:SS`; text that is not a number or a time is refused. |
| `features/review/MonthPicker.test.tsx` | The billing month defaults to the current month, also across a year boundary; the field is labelled and described as the month the card is charged; the connected card agents are named; without any, only that fact is shown, with no month to pick; a month without a review offers Start with the starts left, none before the agents or the month were read, and none once the starts are used, naming when the next is allowed; a month with its review offers Clear instead, held while the review runs; a picked month is reported. |
| `features/review/QuestionCard.test.tsx` | Each merchant lists its rows with date, card, statement text, amount and details; one "continue" button posts the merchants answered plus "continue" to every card agent asking, and is disabled while an answer is in flight; "not sure" drops an answer, offering to keep the card agent's guess; a card agent's "skip" is its own button that posts at once with the categories chosen so far; a question with a link repeats no text, opens the agent's page from a button in a new tab and offers no skip; a `sign-in-required` question shows Google's button, reports the renewed sign-in and offers no skip. |
| `features/review/TotalsChart.test.tsx` | Each category with spend gets a slice, summarized in text for screen readers and shown with amount and share on hover; the legend runs largest first and marks an overrun, a missing limit and a category without a slice; a month with no spend draws no pie; skipped agents are listed; a slice or legend entry selects its category and the Totals heading selects all; the standing-order spend is shown and selects the standing orders. |
| `features/review/ReviewPage.test.tsx` | Without a card agent the page says so and offers no start; a review runs from start to totals and report on its events alone, with its raw transactions folded until opened; the started review's month goes into the URL, and a page opened with a month shows that month's review with its waiting question and Clear instead of Start; picking a month without a review hides the review and offers Start; a month that cannot be read is reported; a question posed again before the answer's 204 stays shown; a failure shows once; a malformed frame and a refused answer are shown; choosing a category in the totals lists only its raw transactions and Totals lists all again; choosing the standing orders lists only them until the box is cleared; a completed review recategorizes a merchant from the raw transactions, which stay read-only until the rerun's report arrives; a refused start is shown; Clear review stays disabled while the review runs, then clears it and offers Start again. |

`scripts/test.sh frontend` also runs `tsc -b`, `oxlint` and `vite build`.

## End to end

`./scripts/test.sh e2e [--amex-dir D]` is the one place both repos meet. It builds amex-agent from
the checkout `--amex-dir` names (default `../../java/amex-agent` beside this repo) and starts the
whole stack as its own compose project, `hfm-e2e`, with a fresh database, the home finance agent
on its canned report (`HFM_E2E`) and amex-agent on its keyword classifier (its `e2e` profile), both
set by `docker-compose.e2e.yml`, which defines the amex-agent service in full so the test reads no
`.env` of that checkout. The agent reads an empty statements folder that test.sh creates with
`mktemp -d`, so it is writable by the host user the agent runs as. Nobody signs in with Google:
`scripts/tests/e2e/make_auth.py` generates a key pair, both agents verify tokens with its public
half under the issuer `hfm-e2e` (`AUTH_PUBLIC_KEY_FILE`, `APP_AUTH_PUBLIC_KEY_FILE`), and it writes
the callers file registering the manager with a throwaway secret and the registry connecting the
manager to amex-agent at its service address with that secret, which test.sh mounts as the
manager's `CARD_AGENTS_FILE`. The script then runs `scripts/tests/e2e/run_review.py` against
`http://localhost:8010`, through the nginx edge, the way a person would: sign in, start a review,
read its event stream, load the missing statement on the agent's page, answer. It refuses to run
while the development stack or an earlier `hfm-e2e` stack is up, and removes the project, its
volume and the folders on every exit.

The script prints one `PASS:` line per check, 21 in all, for a 2026-10 review:

- **Sign-in**: the review API refuses a person who is not signed in; a token signed for the home
  finance agent's client id signs them in and names them.
- **Missing statement**: exactly one remote-input question; it comes from `amex`; its reason is
  `statement-missing`; it offers only `continue`; its link opens the agent's statements page; the
  review is waiting; the answer `skip` is refused; the statements API refuses a person who is not
  signed in; amex-agent's test statement, uploaded through `POST /api/statements` on the link's
  origin with a token for amex-agent's client id, is stored as `2026-10.pdf` and listed for that
  person; the answer `continue` is accepted.
- **Categorize**: exactly one categorize question; it is about the gym, `וים קלאבס בע"מ - הו"`; the
  review is waiting; the answer `health` is accepted; nothing is left uncategorized; health spent
  is 1556.60, the gym's 307.78 included; the report has text.
- The review completed end to end.

"skip" is covered by the graph and runner tests only: the card agent in the end-to-end test names
its page for every missing statement, so no end-to-end question offers it.

On a failure it prints the frames seen so far and the last log lines of the home finance agent and
the agent.

## CI

`.github/workflows/ci.yml` runs on every push and pull request, with two jobs on the same script
developers use:

- `backend`: Python 3.14, `bash scripts/test.sh backend`. The venv installs the runtime
  dependencies at the pins of `backend/requirements.txt`, the lock the image installs, so the suite
  runs on what ships. The Testcontainers database runs on the runner's Docker.
- `frontend`: Node 22, `bash scripts/test.sh frontend`.

The end-to-end test needs the Java repo beside this one, so CI does not run it.
