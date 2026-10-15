"""Fetches a real month from a running card agent; needs AMEX_AGENT_URL and AMEX_AGENT_TOKEN."""
from __future__ import annotations

import os

import pytest

from hfm.adapters.a2a_client import SKILL_ID, A2ACardAgentClient
from hfm.domain.models import AgentConfig
from hfm.ports.card_agent import TaskCompleted, TransactionsBatch

pytestmark = pytest.mark.skipif(
    "AMEX_AGENT_URL" not in os.environ or "AMEX_AGENT_TOKEN" not in os.environ,
    reason="AMEX_AGENT_URL and AMEX_AGENT_TOKEN point at a running card agent",
)

# amex-agent's test statement for this month holds this many transactions.
MONTH = "2026-10"
EXPECTED_TRANSACTIONS = 24


async def test_live_agent_streams_the_covered_month() -> None:
    agent = AgentConfig(
        name="amex",
        url=os.environ["AMEX_AGENT_URL"],
        token=os.environ["AMEX_AGENT_TOKEN"],
        browser_url=os.environ["AMEX_AGENT_URL"],
    )
    adapter = A2ACardAgentClient()
    try:
        info = await adapter.discover(agent)
        events = [event async for event in adapter.fetch_month(agent, MONTH, None)]
    finally:
        await adapter.aclose()

    assert SKILL_ID in info.skills
    batches = [e for e in events if isinstance(e, TransactionsBatch)]
    assert sum(len(b.transactions) for b in batches) == EXPECTED_TRANSACTIONS
    assert isinstance(events[-1], TaskCompleted)
