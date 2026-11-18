# Tools

Hands-on tools, run from any directory against the Compose stack; `--ec2` as the first argument
acts on the stack's EC2 instance. Each prints its full usage with `--help`.

- `add-card-agent.sh [--ec2]` — connects a card agent, or replaces its entry, in the registry of
  this machine (`backend/card-agents.yaml`) or, with `--ec2`, of the instance
  (`backend/card-agents.ec2.yaml`), from the four values its operator sends; `deploy.sh` applies
  it. `add_card_agent.py` beside it writes the entry.
- `sql-helper.sh [--ec2]` — psql on the stack's database: a shell, `-c`, a SQL file, row counts
  and rows of every table, and `--backup <file>` / `--restore <file>` of the whole database.
- `lock.sh` — recompiles `backend/requirements.txt` inside the Dockerfile's Python image; run it
  after editing the dependency list.

Back to the [README](../../README.md).
