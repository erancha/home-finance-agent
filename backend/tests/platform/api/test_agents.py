"""The page learns which card agents are connected before it offers a review."""
from __future__ import annotations

from fastapi.testclient import TestClient

from hfm.platform.api.auth import COOKIE
from hfm.platform.app import create_app
from tests.platform.support import DANA_TOKEN, app_deps, scripted


def signed_in(card_agents: tuple[str, ...]) -> TestClient:
    client = TestClient(create_app(deps=app_deps(scripted(), card_agents=card_agents)))
    client.cookies.set(COOKIE, DANA_TOKEN)
    return client


def test_lists_the_connected_agents_in_registry_order() -> None:
    with signed_in(("amex", "visa")) as client:
        assert client.get("/api/agents").json() == {"agents": ["amex", "visa"]}


def test_lists_none_when_no_agent_is_registered() -> None:
    with signed_in(()) as client:
        assert client.get("/api/agents").json() == {"agents": []}


def test_needs_a_session() -> None:
    with TestClient(create_app(deps=app_deps(scripted()))) as client:
        assert client.get("/api/agents").status_code == 401
