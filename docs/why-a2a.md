# Why A2A, and how much of it this demo uses

An honest account of what the A2A protocol adds between the home finance agent and a card agent,
and where its use here is thinner than the word "agent" suggests. The contract itself is in
[a2a-contract.md](a2a-contract.md); the review's design is in [architecture.md](architecture.md).

**Contents:** [The card agent is mostly a service](#the-card-agent-is-mostly-a-service) ·
[What a plain web call would also cover](#what-a-plain-web-call-would-also-cover) ·
[What only a task protocol covers](#what-only-a-task-protocol-covers) ·
[What the common protocol buys](#what-the-common-protocol-buys) ·
[What would make the agents reason at each other](#what-would-make-the-agents-reason-at-each-other)

## The card agent is mostly a service

A card agent receives one thing, the billing month, and returns one thing, a table of charges in a
fixed shape with a fixed list of categories. Neither side writes to the other in plain language. The
home finance agent never picks between skills, never cancels, and in this demo is the card agent's
only caller. The one place a language model runs on the card side is deciding each merchant's
category, and the home finance agent sees only the result: a category and how sure the card agent
is. On the home finance side the review follows a fixed plan in code, and a model writes only the
summary.

A2A is built for open-ended conversation between agents. Here it carries a fixed question with a
fixed answer. That is a fair use of the protocol, but it is a contract between a planning program
and a categorizing service, not two agents reasoning at each other.

## What a plain web call would also cover

Everything in a month the card agent has: the request, the progress messages shown live on the
page, the charges arriving in batches, and the end, successful or not. One HTTP request answered
with a server-sent event stream carries the same rows. Under the hood A2A over JSON-RPC is exactly
that, an HTTP call whose answer streams back as server-sent events in an agreed format, so "it
could be done with SSE" is true of the protocol as a whole, not a flaw in how this demo uses it.

## What only a task protocol covers

A streamed answer is over when the connection closes. An A2A task is not: it has an id that
outlives the connection. When a card agent has no statement for the month, it parks its task in
`TASK_STATE_INPUT_REQUIRED`, closes the connection, and the home finance agent picks that same task
up later, possibly hours later and after either side restarted, with the person's fresh sign-in
token. An expired token is handled the same way, as a task in `TASK_STATE_AUTH_REQUIRED`, instead
of a failed call.

Doing this with plain web calls means inventing task ids, a "continue" call, a list of task states
and a sign-in-again state. That is rebuilding A2A's task lifecycle privately. This pause and
continue is the one part of the demo that genuinely needs A2A.

## What the common protocol buys

Three things visible in the code, not hypothetical:

- **Discovery and plug-in.** Each card agent publishes a card saying which skill it offers, where
  to call it and which credentials it expects. A new card agent is one `add-card-agent.sh` run and
  no code change.
- **Two implementations that must agree.** The card agent is built on a2a-java and this client on
  the Python a2a-sdk. That boundary surfaced real protocol facts: the blocking `SendMessage` call
  races inside a2a-java, so this client only streams, and a task's state is the thing to trust,
  not the `final` flag beside it. A home-grown format would never be tested against a second
  implementation.
- **One vocabulary.** Working, input required, auth required, completed, failed and canceled
  already mean the same thing to both agents and to the review page in the browser.

## What would make the agents reason at each other

Any of these turns the demo from a service call into a conversation between agents. None is
implemented; they are listed so a reader can tell the deliberate boundary from an oversight.

- The home finance agent sends a goal in plain language, such as "this month's spending, and flag
  anything unusual", and the card agent decides what to pull and asks its own questions in plain
  language.
- The home finance agent finds out at run time which card agents and skills exist and chooses among
  them, instead of reading a configured list.
- The card agent notifies the home finance agent when a statement lands, so a paused review
  resumes without the person pressing "continue".
