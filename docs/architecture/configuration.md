# Configuration

The home finance agent reads three kinds of configuration, each kept where its owner edits it: its
own settings in the environment and `backend/.env`, the connected card agents in
`backend/card-agents.yaml`, and the person's budget in `config/budget.yaml`. A missing or malformed
required value stops startup with its name, rather than letting the agent run on a default nobody
chose.

Every setting is explained in one place, [backend/.env.example](../../backend/.env.example): the
required ones are uncommented, and every optional one is commented out at its default.

## The card-agent registry

The registry is `backend/card-agents.yaml`, or the file `CARD_AGENTS_FILE` names.
`add-card-agent.sh` writes one entry into it per card agent: the card agent's name, the URL this
agent fetches its Agent Card from, the URL a person's browser opens its pages at, and the secret the
card agent issued to this one. The file holds secrets, so the scripts write it readable by its owner
alone and compose runs the container as that owner. An absent file or an empty list means no card
agents: the agent runs and the review page says so. A blank field, a URL that is not http(s) or a
name listed twice stops startup naming the entry. The registry is read at startup, so a change needs
a restart.

The agent calls the URL the card agent's Agent Card advertises, not the one it fetched the card
from, so both must be reachable from where this agent runs. In Docker, an agent on the same
machine is `http://host.docker.internal:<port>`; with `start.sh --host` it is
`http://localhost:<port>`. The hand-over itself is in
[connecting-agents.md](../connecting-agents.md).

## The budget

`config/budget.yaml` holds the currency and a monthly limit per category. It is the person's own
and stays out of the repository; `init-env.sh` starts it from `config/budget.example.yaml`, which
is committed. Every category must come from the shared category list the card agents categorize
against; an unknown one stops startup instead of quietly totalling to zero.

## Other devices on your network

The agent listens on every interface, so any browser on the network reaches the page at this
machine's address. Reaching it is not using it: every review route needs the sign-in cookie, and
Google signs in only a page served from `localhost` or a public hostname, never a private address.
Another device therefore sees the sign-in button and cannot get past it until the stack is reached
through a hostname registered with both agents' Google clients. For another device to follow a
card agent's statement link, register the card agent with this machine's address as its browser
URL. Postgres stays on `127.0.0.1:5434`.

On Windows with WSL2, Docker mode needs nothing more, since Docker Desktop publishes the port on the
Windows side. `start.sh --host` inside WSL2 is reachable from other devices only with WSL's mirrored
networking mode.
