# 0004. Google sign-in, forwarded to each card agent with a caller secret

- Status: Accepted
- Date: 2026-10-21

## Context

Anyone who opened the page could start a review, and every review and remembered merchant
belonged to nobody in particular. Calls to amex-agent carried one fixed token that both
repositories knew, and this repository's env file and Compose file named amex-agent, so neither
agent could be set up or started without the other. A card agent serves one person's statements
and needs to know both which caller is asking and for whom.

## Decision

- People sign in with their Google account only, through an OAuth client that belongs to this
  agent. The backend verifies the ID token with PyJWT against the keys Google publishes, accepts
  only tokens issued to its own client, and keeps the token in an HttpOnly cookie it verifies on
  every request.
- Reviews, events, checkpoints and memories are keyed by the Google account id, so a person sees
  only their own.
- Every A2A call carries the person's token as a bearer token and a secret the card agent issued
  to this agent. The card agent verifies both.
- The token reaches the call through a context variable, never through checkpointed state.
- The card agents are listed in `backend/card-agents.yaml`, written by `add-card-agent.sh`; an
  absent file means none, and the agent runs on its own.

## Consequences

- Each card agent's operator registers this agent's Google client id and hands back four values:
  its name, its URL, the URL a browser opens its pages at, and the secret.
- The person signs in to the card agent's pages with the same Google account.
- Google accepts only `localhost` or a public hostname as an origin, so another device on the home
  network cannot sign in until the stack has a hostname.
- A test searches every checkpoint blob for the token and the secret.
