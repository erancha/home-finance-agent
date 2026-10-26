# Configuration

`platform/config.py` reads the environment and `.env` in the working directory; a blank value counts
as unset. The scripts export `backend/.env` into the environment, and compose passes it to the
containers; a variable already exported in the calling shell keeps its value, even over a blank line
in the file (`scripts/common.sh` `load_env`, checked by `scripts/tests/test_load_env.sh`). The app
refuses to start when a required key is missing.

| Key | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | SQLAlchemy URL, `postgresql+psycopg://...`; the checkpointer uses the same database. |
| `LLM_MODEL` | yes, unless `HFM_E2E` | `anthropic:<model>` or `openai:<model>`. |
| `LLM_API_KEY` | yes, unless `HFM_E2E` | The API key of the provider `LLM_MODEL` names. |
| `HFM_E2E` | no | Set by `docker-compose.e2e.yml` alone: the report is a canned text and no model or key is read. |
| `GOOGLE_CLIENT_ID` | yes | The OAuth client of this agent's sign-in button; the audience every accepted token names. |
| `AUTH_ISSUER`, `AUTH_JWKS_URL` | no | Who issues tokens and where its keys are; Google's by default. |
| `AUTH_PUBLIC_KEY_FILE` | no | Test only: a PEM key that replaces the JWKS fetch. |
| `CARD_AGENTS_FILE` | no | The card-agent registry; default `backend/card-agents.yaml`, which compose mounts at `/card-agents.yaml`. Absent or empty: no card agents. |
| `BUDGET_CONFIG` | no | Default `config/budget.yaml`. |
| `HFM_FRONTEND_DIST` | no | Built page folder served at `/`; unset serves the API only. |
| `REDIS_URL` | no | A Redis that carries live events between replicas; compose sets it to its `redis` service. Unset, live events stay in the one process. |
| `REPORT_MEMORY_RETENTION_DAYS` | no | How long a written report answers for the same totals instead of the model; default 90. |

Keys read outside the settings class: `LANGGRAPH_STRICT_MSGPACK` (LangGraph itself),
`HFM_LOG_LEVEL` and `HFM_LOG_LEVELS` (`platform/logging.py`). `backend/.env.example` explains
each; `tests/test_env_example.py` keeps that file and the code in step. The scripts export
`CARD_AGENTS_FILE` for the compose mount, and `start.sh` refuses to launch while the registry file
is missing, since a bind mount of a missing path would create a directory there; `init-env.sh`
creates it empty.

**`backend/card-agents.yaml`**, the registry `scripts/add-card-agent.sh` writes (gitignored, mode
600), lists the card agents by `name` with `url`, the address the manager fetches the card from,
`browser_url`, the address a person's browser opens the agent's pages at, and `shared_secret`, the
secret the agent issued to this one. The manager fetches the card at `url` and calls the URL the
card advertises, which its start script prints, so both must be reachable from where the manager
runs, and an unreachable call names the advertised address when it differs from the registered one.
An absent file or `agents: []` means no card agents: the manager runs, and the page says so. A blank
field, a non-http(s) URL or a name listed twice stops startup naming the entry
(`adapters/config_files.load_card_agents`). The file holds the agents' secrets, so the scripts write
it readable by its owner alone, and compose runs the manager container as that user (`user:` from
`HOST_UID`/`HOST_GID`, which `load_env` exports) so the read-only mount is readable inside it; the
image's own user `hfm` serves the migration run.

In Docker the manager reaches an agent on the same machine as `http://host.docker.internal:<port>`;
compose gives the container that name (`extra_hosts: host-gateway`), which Docker Desktop provides
on its own. In `--host` mode the manager is a host process, so the agent is registered, and
advertises itself, as `http://localhost:<port>`.

**`config/budget.yaml`** holds the `currency` and a monthly limit per category. Every category must
be in the shared taxonomy (`domain/taxonomy.py`, the list the card agents categorize against); an
unknown one stops startup rather than totalling to zero.

## Other devices on your network

The home finance agent listens on every interface in both modes (compose publishes `8010:8010` on
the edge; `start.sh --host` runs uvicorn with `--host 0.0.0.0`), and the page calls its API by
relative paths, so any browser on the network can reach `http://<this machine's address>:8010`.
Reaching it is not using it: every review route needs the sign-in cookie, and Google issues a token
only to a page served from an authorized origin, which must be `localhost` or a public hostname,
never a private address. So another device on the network sees the sign-in button and cannot get
past it until the
stack is reached through a hostname registered with both Google clients. The browser opens only
a card agent's page, from a missing-statement question's link; everything else on a card agent is
called by the home finance agent, and a card agent publishes and guards its own port from its own
repo. The link uses the agent's `browser_url` in the registry, so for another device to follow it,
register the agent with this machine's address as its browser URL. Postgres stays on
`127.0.0.1:5434`.

On Windows with WSL2 and Docker Desktop, Docker mode needs nothing more: Docker Desktop serves the
published port on the Windows side, so other devices use the Windows machine's address.
`start.sh --host` inside WSL2 is different: in the default NAT networking, WSL's own address is
unreachable from the network, so other devices need Docker mode or WSL's mirrored networking mode
(`networkingMode=mirrored` in `.wslconfig`).

## Report providers

`adapters/report_writer.py` turns `LLM_MODEL` into a writer. `provider:model` goes to LangChain's
`init_chat_model` with `LLM_API_KEY`; `anthropic` and `openai` are supported. An OpenAI GPT-5
model is asked for minimal reasoning effort, since it only phrases totals computed in code and
takes over a minute on its default. Only the
end-to-end test, through `HFM_E2E`, gets the canned writer, which returns a fixed paragraph without
calling any model.
