# CLAUDE.md

The home finance agent half of a two-repo A2A demo: a Python LangGraph review (FastAPI, Postgres,
React page) that is the A2A client of card agents such as amex-agent, deployed separately from
their own repos. Layout, layers and parts: docs/architecture.md; the contract every card agent
offers: docs/a2a-contract.md. It is a Docker Compose repo, aligned with loan-simulator, the
reference repo of the Docker Compose repos. The checkout belongs on the WSL ext4 filesystem, not
under `/mnt/c`; docs/development.md explains the cost.

## Operations scripts (scripts/)

Every script sources `scripts/common.sh`, which exports the three settings files under
`scripts/lib/` before it calls Compose: the committed `stack-params.sh`, and the gitignored
`params.sh` and `secrets.sh`, each beside an `.example.sh` that documents its keys. A bare
`docker compose` call therefore has no settings. `.githooks/pre-commit` refuses a commit that
stages one of the gitignored files, a value of `secrets.sh`, or an address of `params.sh` other
than the license contact (`PUBLISHED_SETTINGS` of `lib/settings-guard.sh`).

- Compose hands each container only the keys it reads, listed once per service, and overrides
  `DATABASE_URL` with the in-network address, so the files hold the host form. Host commands
  (pytest, uvicorn) run from the repo root, because the manager reads the settings files by their
  path from the working directory.
- Nothing is bind-mounted, so the same Compose file runs against the EC2 instance's daemon: the
  edge bakes `nginx/default.conf` into `hfm-edge`, the manager image bakes `config/budget.yaml`,
  and the card-agent registry is a Compose secret from `CARD_AGENTS_REGISTRY`, which `compose()`
  reads from `backend/card-agents.yaml` (on EC2 `CARD_AGENTS_EC2_REGISTRY`, from
  `backend/card-agents.ec2.yaml`). A registry or budget edit takes a `deploy.sh` run.
- The manager calls the URL a card agent's card advertises, which must be reachable from its
  container: `http://host.docker.internal:<port>` for a card agent on the same machine or
  instance.
- The layer rule, enforced by `lint-imports` from `backend/pyproject.toml`: package `hfm` in
  `backend/src` is `platform → application → ports → domain`; `adapters` import only `ports`
  and `domain`. `domain`, `ports` and `application` import no framework; only
  `application/review_graph.py` may import `langgraph`.
- a2a-sdk 1.x types are protobuf: use `HasField`, `TaskState.Name(state)`, `get_data_parts`, not
  attribute checks or dicts. Wire task states are `TASK_STATE_*`; key on the state, never the
  `final` flag, since the card agent closes the stream right after `TASK_STATE_INPUT_REQUIRED`.
  Stream only (`SendStreamingMessage`); the blocking `SendMessage` races inside a2a-java.
- Numbers never come from the model: totals are computed in code and only narrated by it.
- Every runner method acts for a `User`; the person's ID token reaches the A2A call through
  `application/user_token.py` (a context variable), never through state or config, and a test
  searches every checkpoint blob for it. Tests sign their own tokens (`tests/auth_keys.py`).
- Checkpointed state types must be in `CHECKPOINTED_TYPES`; the tests run with
  `LANGGRAPH_STRICT_MSGPACK=true` and fail on any checkpoint warning. Answers are validated in
  the runner before resuming: a bad resume value is replayed by LangGraph on every later resume.
- Review failures are read by the person: `AgentUnusableError` and `TaskFailed` texts are
  predicates after the agent name (`amex could not be reached at ...`).
- Before any AWS work, read this account's inventory, the
  `aws-account-inventory-<account ID>.md` under `/mnt/c/Projects/-- docs --/` that lists
  the stacks deployed there and which one hosts the instance.
- `test.sh [all|backend|frontend|e2e [--amex-dir D]]` (aliases `be`, `fe`) — the whole quality
  gate: bash syntax check and the shell tests of `scripts/tests/`, ruff, mypy, import-linter and
  pytest for `backend/`; oxlint, Vitest, `tsc` and the Vite build for `frontend/`. `e2e` is
  opt-in, the one place both repos meet; merchant memory persists, so it runs as its own Compose
  project with a fresh database.
- `init-env.sh [--force]` — creates each missing gitignored `scripts/lib/secrets.sh`,
  `params.sh` and `aws-config.sh` from its `.example.sh`, with a generated database password,
  plus both empty registries and `config/budget.yaml`; an existing settings file is kept unless
  `--force` is given, a registry or budget always.
- `deploy.sh` — runs `init-env.sh` first and stops on a list of every required setting still blank,
  then builds and runs Postgres (with its schema migration), Redis, two manager replicas and the
  nginx edge in Docker Compose, returns once the page answers on 8010, and prints the Google client
  id a card agent registers this agent with; `--ec2` does it on an EC2 instance, its own or another
  repo's as a guest (`EC2_HOST_STACK` of `params.sh`), behind its own CloudFront
  (`template-ec2.yaml`, `docker-compose.ec2.yml`), in the account of the gitignored
  `lib/aws-config.sh`.
- `docker-helper.sh [--ec2]` — `--stop [--volumes]`, `--logs [-e] [service...]`, `--ps`;
  `--ec2 --delete-stack` deletes this repo's EC2 stack.
- `lib/ec2.sh` — the EC2 target: the stack's deploy, SSH with an Instance Connect key, Compose
  against the instance's daemon. `lib/settings-guard.sh` — the checks behind the pre-commit
  hook. Both are the same files in every Docker Compose repo.
- `tools/add-card-agent.sh [--ec2]` — connects a card agent in the registry of this machine or
  of the instance.
- `tools/sql-helper.sh [--ec2]` — psql on the stack's database; `--counts`, `--rows`,
  `--backup <file>`, `--restore <file>`.
- `tools/lock.sh` — recompiles `backend/requirements.txt` inside the Dockerfile's Python image
  after editing the dependency list.
