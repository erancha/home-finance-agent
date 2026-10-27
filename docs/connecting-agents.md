# Connecting the home finance agent to a card agent

The two agents are deployed separately, each from its own repo by its own operator, and connected
afterwards by four values handed over out of band. This page walks through both sessions in
order. Each repo's README covers its own session; the Google side of this agent is in
[sign-in.md](sign-in.md).

## Session A: the home finance agent, nothing else deployed

1. `./scripts/init-env.sh` writes `backend/.env` and an empty card-agent registry.
2. Create its Google Cloud project and OAuth client, with `http://localhost:8010` as the authorized
   JavaScript origin ([sign-in.md](sign-in.md#setting-up-google)), and put the client id in
   `backend/.env` as `GOOGLE_CLIENT_ID`, with the model key as `LLM_API_KEY`.
3. `./scripts/start.sh`. Open http://localhost:8010 and sign in. The page says "No card agents are
   connected yet." and offers no review. Nothing in this session has named a card agent.
4. `start.sh` ends by printing the Google client id. It is public; hand it to the card agent's
   operator, who registers this agent as a caller with it.

## Session B: the card agent, from its own repo

Its README's Getting started covers its Google client, its env file and its start. This guide
relies on two things every card agent does:

1. Its registration script takes this agent's name and Google client id (A4), issues the
   secret, and prints the four values: the name to register it under, the URL this agent calls
   it at, the URL a person's browser opens its pages at, and the secret, shown once. They become
   `--name`, `--url`, `--browser-url` and `--secret` in step 5.
2. Its start script repeats the three public values once the agent is healthy. A card agent may
   be recorded here before or after its first start; it has to be running when a review begins.

The URL it prints is the one its card advertises, and this agent calls that URL rather than the
one it fetched the card from, so the card agent's operator sets it to an address reachable from
where this agent runs: `http://host.docker.internal:<port>` for a card agent on the same machine
when this agent runs in Docker, `http://localhost:<port>` when it runs with `start.sh --host`, the
card agent's hostname when it runs elsewhere.

## Session A again: connect and restart

5. `./scripts/add-card-agent.sh --name <name> --url <url> --browser-url <browser url> --secret
   <secret>`, with the values from B. This writes `backend/card-agents.yaml`; `backend/.env` is
   untouched.
6. `./scripts/start.sh` again. Compose recreates the agent's replicas with the registry; the
   database and its reviews stay. The page reads "Registered card agents: <name>" and offers a
   review.
7. Start a review. Before any statement is loaded it pauses with a link to the card agent's
   statements page: sign in there with the same Google account, load the month's statement, come
   back and press "continue". What the page says when something is off:

   | Condition | Review failed: ... |
   |---|---|
   | the card agent is not running | `<name> could not be reached at <url>; it may not be running` |
   | the card agent advertises an address this agent cannot reach (a `localhost` URL with this agent in Docker) | `<name> could not be reached at <advertised url>, the address its card advertises (registered at <url>); it may not be running` |
   | the registered secret is wrong | `<name> refused this agent's secret; check its registration` |
   | the card agent has no statement for the month | not a failure: the review pauses with a link to its pages and a "continue" |

   Starting again once the card agent is up works without restarting this agent.

## Changing or revoking

Edit the registry on whichever side changed, with its script, and restart that agent only: the
card agent's registration script replaces a caller's entry (a new secret means a new hand-over);
`add-card-agent.sh` replaces a card agent's entry. Removing an entry is editing the file.

## Why four values and a URL rule

The secret proves to the card agent which caller is asking; the Google client id lets it check that
the forwarded tokens were issued to that caller's sign-in; the URLs are where this agent calls and
where a person's browser goes. This agent fetches the card at the registered URL but calls the URL
the card advertises, so the advertised one must be the one callers can reach.

[amex-agent](https://github.com/erancha/amex-agent), the demo's card agent, follows this:
its README's Getting started covers the registration and the hand-over.
