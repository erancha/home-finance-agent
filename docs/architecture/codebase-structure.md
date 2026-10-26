# Codebase structure

One package, `hfm`, under `backend/src`, in five layers:

| Layer | Holds | Modules |
|---|---|---|
| `domain` | Plain immutable values and the rules on them: transactions, budget, totals, questions, events, the category list, merchant keys, the signed-in person, errors. | `models`, `taxonomy`, `merchants`, `questions`, `events`, `errors` |
| `ports` | The interfaces the review needs from the outside world, as Python protocols. | `card_agent`, `repositories`, `events`, `report`, `auth` |
| `application` | The review itself: the graph, totals arithmetic, questions and answer checks, the report prompt, the event sink, the run-scoped user token. | `review_graph`, `reconcile`, `questions`, `report`, `event_sink`, `user_token` |
| `adapters` | Port implementations: the A2A client, Postgres repositories, the report writers, the Google token verifier, YAML config loading, the in-process and the Redis event bus. | `a2a_client`, `postgres/`, `report_writer`, `google_tokens`, `config_files`, `memory_bus`, `redis_bus` |
| `platform` | The running process: settings, logging, database engine, checkpointer, the review runner and the HTTP API. | `config`, `logging`, `db`, `checkpointer`, `review_runner`, `app`, `dependencies`, `api/` |

Imports point inwards only. `platform` may use everything; `application` uses `ports` and
`domain`; `ports` uses `domain`; `adapters` use `ports` and `domain` and never `application` or
`platform`. `domain`, `ports` and `application` import no framework, so the review's rules can be
tested on plain values and fakes. The one exception is LangGraph, which only the review graph may
import, because the graph is the review's orchestration.

These rules are import-linter contracts in `backend/pyproject.toml`, checked on every backend test
run.
