# CLAUDE.md

The home finance agent half of a two-repo A2A demo: a Python LangGraph review (FastAPI, Postgres,
React page) that is the A2A client of card agents such as amex-agent, deployed separately from
its own repo. README.md tells the story;
`docs/architecture.md`, `docs/a2a-contract.md` and `docs/testing.md` hold the details.

## Layout and the layer rule

Package `hfm` in `backend/src`: `platform → application → ports → domain`; `adapters` import only
`ports` and `domain`. `domain`, `ports` and `application` import no framework; only
`application/review_graph.py` may import `langgraph`. `lint-imports` enforces this from
`backend/pyproject.toml`.

## Scripts

- `./scripts/init-env.sh [--force]`: create `backend/.env` and an empty `backend/card-agents.yaml`.
- `./scripts/add-card-agent.sh --name N --url U --browser-url B --secret S`: connect a card agent;
  the manager reads the registry at startup.
- `./scripts/start.sh [--host]`: run db, migrations and the agent; the page is
  http://localhost:8010, Postgres 127.0.0.1:5434. Ends by printing the Google client id a card
  agent registers this agent with.
- `./scripts/docker-helper.sh --stop [--volumes] | --logs [-e] | --ps`.
- `./scripts/sql-helper.sh [--counts | --rows | -f <file> | psql-args]`: psql on the stack's
  database; `--counts`/`--rows` run `scripts/sql/all-tables.sql`.
- `./scripts/test.sh [backend | frontend[=unit] | e2e [--amex-dir D]]`: the gate is `backend` +
  `frontend`; the e2e is the one place both repos meet.

`backend/.env` holds only this agent's settings; card agents live in `backend/card-agents.yaml`
(`CARD_AGENTS_FILE`), absent means none. In Docker an agent on this machine is
`http://host.docker.internal:<port>`.

## Facts that bite

- a2a-sdk 1.x types are protobuf: use `HasField`, `TaskState.Name(state)`, `get_data_parts`, not
  attribute checks or dicts.
- Wire task states are `TASK_STATE_*`. Key on the state, never the `final` flag; the agent closes
  the stream right after `TASK_STATE_INPUT_REQUIRED`.
- Stream only (`SendStreamingMessage`); the blocking `SendMessage` races inside a2a-java.
- Numbers never come from the model: totals are computed in code and only narrated by it.
- Every runner method acts for a `User`; the person's ID token reaches the A2A call through
  `application/user_token.py` (a context variable), never through state or config, and a test
  searches every checkpoint blob for it. Tests sign their own tokens (`tests/auth_keys.py`).
- Checkpointed state types must be in `CHECKPOINTED_TYPES`; the tests run with
  `LANGGRAPH_STRICT_MSGPACK=true` and fail on any checkpoint warning.
- Answers are validated in the runner before resuming: a bad resume value is replayed by LangGraph
  on every later resume.
- Merchant memory persists across reviews, so the e2e needs a fresh database (its own compose
  project).
- Review failures are read by the person: `AgentUnusableError` and `TaskFailed` texts are
  predicates after the agent name (`amex could not be reached at ...`).
