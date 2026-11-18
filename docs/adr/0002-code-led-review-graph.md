# 0002. A code-led review graph pauses for the person; the model only narrates

- Status: Accepted
- Date: 2026-10-15

## Context

A review of one month gathers each card's charges, asks the person about the merchants and the
missing statements it cannot settle alone, adds up the totals against a budget and writes a short
summary. An answer may come hours later, after the backend has restarted. The person relies on
the totals, so a figure that a language model made up or misread would make the review worthless,
while a few sentences of plain prose about the totals help them read the month.

## Decision

- The review is a fixed plan written in code: a LangGraph state machine in
  `application/review_graph.py`, the one module allowed to import LangGraph.
- A question pauses the graph. Its state is checkpointed in Postgres (ADR 0003), so the review
  waits for the answer across restarts and resumes from the checkpoint.
- Totals are computed in code with exact decimals and compared to the budget there.
- A language model gets only the computed totals and writes the summary. `LLM_MODEL` names an
  Anthropic or OpenAI model, reached through LangChain.

## Consequences

- No number the person sees comes from the model, and every test runs without a model key.
- Every type held in a checkpoint must be on an allow-list, and the tests fail on any checkpoint
  warning, so state survives a restart intact.
- An answer is validated before the graph resumes, since a bad resume value would be replayed on
  every later resume.
- A new kind of question is a change to the graph in code, never an improvised turn by the model.
