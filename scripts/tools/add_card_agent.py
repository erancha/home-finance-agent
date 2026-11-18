"""Writes one card agent's entry into a registry for add-card-agent.sh, replacing any entry of
the same name and keeping the others, and leaves the file readable by its owner only.

It reads back only the shape it writes, plus the empty registry init-env.sh writes; anything else
is refused rather than guessed at.

    python3 add_card_agent.py <registry> <name> <url> <browser url> <secret>
"""

import os
import re
import sys

FIELDS = ("url", "browser_url", "shared_secret")
ENTRY = re.compile(r"^  - name: (\S+)$")
FIELD = re.compile(r"^    (url|browser_url|shared_secret): (\S+)$")
HEADER = (
    "# Card agents this home finance agent reviews with;"
    " written by scripts/tools/add-card-agent.sh."
)


def read_agents(path: str) -> list[dict[str, str]]:
    agents: list[dict[str, str]] = []
    if not os.path.exists(path):
        return agents
    current: dict[str, str] | None = None
    with open(path, encoding="utf-8") as registry:
        for number, line in enumerate(registry, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#") or line in ("agents:", "agents: []"):
                continue
            if entry := ENTRY.match(line):
                current = {"name": entry.group(1)}
                agents.append(current)
            elif (field := FIELD.match(line)) and current is not None:
                current[field.group(1)] = field.group(2)
            else:
                sys.exit(f"{path}:{number}: not a line add-card-agent.sh writes: {line}")
    for agent in agents:
        if set(agent) != {"name", *FIELDS}:
            sys.exit(f"{path}: entry {agent.get('name')} lacks one of {', '.join(FIELDS)}")
    return agents


def main(path: str, name: str, url: str, browser_url: str, secret: str) -> None:
    agents = [agent for agent in read_agents(path) if agent["name"] != name]
    agents.append({"name": name, "url": url, "browser_url": browser_url, "shared_secret": secret})
    lines = [HEADER, "agents:"]
    for agent in agents:
        lines.append(f"  - name: {agent['name']}")
        lines += [f"    {field}: {agent[field]}" for field in FIELDS]
    with open(path, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    main(*sys.argv[1:])
