# CLAUDE.md

The home finance agent half of a two-repo A2A demo: a Python LangGraph review (FastAPI, Postgres,
React page) that is the A2A client of the Java card agent, amex-agent. README.md tells the story;
`docs/architecture.md`, `docs/a2a-contract.md` and `docs/testing.md` hold the details.

## Layout and the layer rule

Package `hfm` in `backend/src`: `platform → application → ports → domain`; `adapters` import only
`ports` and `domain`. `domain`, `ports` and `application` import no framework; only
`application/review_graph.py` may import `langgraph`. `lint-imports` enforces this from
`backend/pyproject.toml`.

## Scripts

- `./scripts/init-env.sh [--force | --sync-token] [--amex-dir D]`: create `backend/.env`, share the
  token with the agent.
- `./scripts/start.sh [--host]`: run the stack; the page is http://localhost:8010, the agent
  http://localhost:8020, Postgres 127.0.0.1:5434.
- `./scripts/docker-helper.sh --stop [--volumes] | --logs [-e] | --ps`.
- `./scripts/sql-helper.sh [--counts | --rows | -f <file> | psql-args]`: psql on the stack's
  database; `--counts`/`--rows` run `scripts/sql/all-tables.sql`.
- `./scripts/test.sh [backend | frontend[=unit] | e2e]`: the gate is `backend` + `frontend`.

`backend/.env` names the Java repo (`AMEX_AGENT_DIR`) and its statements folder
(`AMEX_STATEMENTS_DIR`); neither has a default.

## Facts that bite

- a2a-sdk 1.x types are protobuf: use `HasField`, `TaskState.Name(state)`, `get_data_parts`, not
  attribute checks or dicts.
- Wire task states are `TASK_STATE_*`. Key on the state, never the `final` flag; the agent closes
  the stream right after `TASK_STATE_INPUT_REQUIRED`.
- Stream only (`SendStreamingMessage`); the blocking `SendMessage` races inside a2a-java.
- Numbers never come from the model: totals are computed in code and only narrated by it.
- Checkpointed state types must be in `CHECKPOINTED_TYPES`; the tests run with
  `LANGGRAPH_STRICT_MSGPACK=true` and fail on any checkpoint warning.
- Answers are validated in the runner before resuming: a bad resume value is replayed by LangGraph
  on every later resume.
- Merchant memory persists across reviews, so the e2e needs a fresh database (its own compose
  project).
