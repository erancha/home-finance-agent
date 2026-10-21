"""Fetches a real month from a running card agent; needs LIVE_AGENT_URL, LIVE_AGENT_TOKEN and
LIVE_AGENT_USER_TOKEN, an ID token the agent accepts for the caller registered with that secret."""
from __future__ import annotations

import os

import pytest

from hfm.adapters.a2a_client import SKILL_ID, A2ACardAgentClient
from hfm.domain.models import AgentConfig
from hfm.ports.card_agent import TaskCompleted, TransactionsBatch

REQUIRED = ("LIVE_AGENT_URL", "LIVE_AGENT_TOKEN", "LIVE_AGENT_USER_TOKEN")
pytestmark = pytest.mark.skipif(
    any(name not in os.environ for name in REQUIRED),
    reason=f"{', '.join(REQUIRED)} point at a running card agent and a person it accepts",
)

# amex-agent's test statement for this month holds this many transactions.
MONTH = "2026-10"
EXPECTED_TRANSACTIONS = 24


async def test_live_agent_streams_the_covered_month() -> None:
    agent = AgentConfig(
        name="amex",
        url=os.environ["LIVE_AGENT_URL"],
        token=os.environ["LIVE_AGENT_TOKEN"],
        browser_url=os.environ["LIVE_AGENT_URL"],
    )
    adapter = A2ACardAgentClient()
    try:
        info = await adapter.discover(agent)
        events = [
            event
            async for event in adapter.fetch_month(
                agent, MONTH, None, os.environ["LIVE_AGENT_USER_TOKEN"]
            )
        ]
    finally:
        await adapter.aclose()

    assert SKILL_ID in info.skills
    batches = [e for e in events if isinstance(e, TransactionsBatch)]
    assert sum(len(b.transactions) for b in batches) == EXPECTED_TRANSACTIONS
    assert isinstance(events[-1], TaskCompleted)
