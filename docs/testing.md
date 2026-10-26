# Testing

What each layer of tests proves, and how to run it. The gate is the backend and the frontend; the
end-to-end test is the one place this repo and a card agent's repo meet.

```bash
./scripts/test.sh                  # backend + frontend
./scripts/test.sh backend          # lint, types, import boundaries, pytest
./scripts/test.sh frontend         # typecheck, lint, component tests, production build
./scripts/test.sh frontend=unit    # typecheck and component tests only
./scripts/test.sh e2e              # a full review through both agents in Docker
```

The backend suite needs Docker for its throwaway Postgres and Redis. No test needs a model key,
and none reaches Google: the tests sign their own tokens with a key pair of their own and verify
them through the same code path the running agent uses.

## Backend

**Static gates** fail the run before any test: ruff, mypy, and the import-linter contracts that
keep the layers pointing inwards ([codebase-structure.md](architecture/codebase-structure.md)).
Shell tests check the scripts an operator runs: the env file never overrides an exported variable,
the registry is written owner-readable and replaced by name, and a launch without the registry is
refused.

**Domain and application** run on plain values and in-memory fakes of every port. They prove the
arithmetic and the rules: totals in exact decimals with overruns marked, a remembered category
outranking the card agent's, a row resent after a "continue" counted once, which rows become
questions, which answer sets are refused, and how expected standing orders and installments are
projected onto a month in progress.

**Adapters** each meet the real thing or a faithful stand-in. The A2A client is driven by scripted
streams covering every task state, malformed cards and rows, and the readable message for each
connection failure. The token verifier refuses every kind of bad token. The Postgres repositories
and the Redis event bus run on real containers, so the one-standing-review rule, concurrent event
appends and cross-replica delivery are checked where they actually hold.

**Graph** runs the real review graph on fakes with the review's own checkpoint serializer: the happy
path, pauses and resumes, "continue" and "skip", several card agents, failures naming the agent, and
recategorizing a finished review. Two guards protect the checkpoints. One searches every stored
checkpoint blob for the caller secret and the person's token and fails on either. The other fails
any test that makes LangGraph warn about a checkpointed type, so a type missing from the allow-list
cannot slip through.

**Runner and API** drive the review runner and the HTTP routes: status changes logged as events,
answers validated before the graph resumes, an answer that races the pause held until the run
settles, the rationing of starts, every route refusing a person who is not signed in, and another
person's review answering 404. The event-stream tests check that replay and live events arrive once
each, and run real uvicorn to prove a shutdown signal ends open streams.

**Database restarts** are simulated by terminating every server connection; the checkpointer and the
repositories must read again without a restart of the agent. A migration test proves the checkpoint
tables belong to the migration run, so replicas starting together never race to create them.

**Repository rules** pin the shape of the deployment: dependencies locked on the image's Python,
the README's contents links reaching headings, Postgres published on localhost only, only the edge
published on every interface, the edge picking up new replicas without a restart, and the env
example documenting every setting.

## Frontend

Component tests in Vitest and Testing Library, with stand-ins for the browser's event stream and
Google's sign-in script. They prove the React page renders a review from its events alone: questions
only once the review is waiting, totals and the pie from the latest totals event, the report,
failures and malformed frames shown. They also cover sign-in and sign-out, the month picker's
rationing, the question card's answers, recategorizing from the raw transactions, and the
expected-charges toggle. `scripts/test.sh frontend` adds the type check, the linter and the
production build.

## End to end

`./scripts/test.sh e2e` builds amex-agent from its checkout beside this repo (`--amex-dir` names
another) and runs both agents in Docker as a separate compose project with a fresh database, since
merchant memory would otherwise answer the questions the test expects. The home finance agent
writes a canned report and amex-agent categorizes by keywords, so no model is called. Nobody signs
in with Google: the script generates a key pair that both agents trust and registers the two agents
with each other using a throwaway secret.

The test then acts as a person would, through the edge: sign in, start a review of 2026-10, meet the
missing-statement question, upload amex-agent's test statement on its page, continue, answer the one
merchant question, and check the totals and the report. It prints one `PASS:` line per check and,
on a failure, the frames seen so far and both agents' last log lines. "skip" is covered by the graph
and runner tests, since the test's card agent always names a page for a missing statement.

## CI

GitHub Actions runs the backend and the frontend jobs on every push and pull request, through the
same `scripts/test.sh` developers use; the backend installs the pins the image ships. The
end-to-end test needs the Java repo beside this one, so CI does not run it.
