"""Checks the nginx edge's config.

The edge proxies to the manager service by name, and that name must be resolved while nginx runs:
replicas added with --scale or recreated by a redeploy get new addresses, and an edge that resolved
the name once at its own start would keep sending to the old ones until restarted.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGE_CONF = ROOT / "nginx" / "default.conf"


def _upstream_block() -> str:
    match = re.search(
        r"^upstream manager \{(.*?)^\}", EDGE_CONF.read_text(), re.MULTILINE | re.DOTALL
    )
    assert match is not None, "no upstream manager block"
    return match.group(1)


def test_the_edge_resolves_the_manager_name_while_running():
    block = _upstream_block()
    assert re.search(r"^\s*resolver 127\.0\.0\.11 .*valid=\d+s;", block, re.MULTILINE), block
    assert re.search(r"^\s*server manager:8010 resolve;", block, re.MULTILINE), block


def test_the_edge_logs_which_replica_served_each_request():
    conf = EDGE_CONF.read_text()
    match = re.search(r"^log_format (\w+) (.*?);", conf, re.MULTILINE | re.DOTALL)
    assert match is not None, "no log_format"
    name, fields = match.groups()
    assert "$upstream_addr" in fields, fields
    assert re.search(rf"^\s*access_log \S+ {name};", conf, re.MULTILINE), conf
