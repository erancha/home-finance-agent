# 0001. Card data comes from card agents over one A2A contract

- Status: Accepted
- Date: 2026-10-15

## Context

A household pays with cards from several issuers, and each issuer's monthly statement has its own
file format, its own labels and its own way of writing installments and foreign purchases. A
review of the month's spending needs every card's charges in one shape, with each merchant placed
in a category. The demo has one card so far, an American Express card, served by amex-agent, a
Java service in its own repository, and a second issuer's card is meant to join without a code
change here. A2A (Agent2Agent) is an open protocol for one agent to hand a task to another and
follow its progress as a stream.

## Decision

- The home finance agent is the A2A client of one card agent per card issuer. It speaks A2A 1.0
  over JSON-RPC with the official Python `a2a-sdk`, and streams every call.
- Every card agent offers the same skill, `monthly-transactions`: a billing month in, rows out in
  one shared format (ISO dates, amounts in shekels, one category from a closed list with the card
  agent's confidence), or a request for the statement it does not have yet.
- Each card agent parses, normalizes and categorizes its own card. The home finance agent owns
  only what spans cards: the person's own categories, the budget, the totals and the summary.
- The A2A client checks every row it receives against the shared format.

## Consequences

- Adding a card means running its agent and listing it in this agent's configuration, with no
  code change here.
- A paused task, such as a missing statement, is part of the protocol: the review pauses on it
  and resumes the same task when the person continues.
- The home finance agent cannot see how a card agent reached a category; it sees only the
  category and how sure the card agent is.
- A2A is used thinly: one skill, no free-text exchange between the agents. `docs/why-a2a.md`
  weighs what the protocol adds here.
