from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hfm.adapters.postgres.repositories import PostgresReviewRepository
from hfm.domain.events import REVIEW_FAILED
from hfm.domain.models import Review, ReviewStatus
from hfm.platform.api.auth import COOKIE
from hfm.platform.app import create_app
from hfm.platform.config import Settings
from hfm.platform.db import build_engine, session_factory
from hfm.platform.review_runner import INTERRUPTED_MESSAGE, ReviewRunner
from tests.auth_keys import CLIENT_ID, PUBLIC_PEM, sign
from tests.platform.support import DANA, MONTH, OTHER_MONTH, app_deps, scripted

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config"


UNREACHABLE_DATABASE = "postgresql+psycopg://u:p@127.0.0.1:1/d"

# One card agent nobody listens on, so a review fails at discovery.
REGISTRY = """agents:
  - name: amex
    url: http://127.0.0.1:1
    browser_url: http://localhost:8020
    shared_secret: token
"""


@pytest.fixture(scope="module")
def registry(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("registry") / "card-agents.yaml"
    path.write_text(REGISTRY)
    return path


@pytest.fixture(scope="module")
def public_key(tmp_path_factory: pytest.TempPathFactory) -> Path:
    pem = tmp_path_factory.mktemp("auth") / "public.pem"
    pem.write_bytes(PUBLIC_PEM)
    return pem


def settings(
    database_url: str = UNREACHABLE_DATABASE, public_key: Path | None = None,
    registry: Path = Path("/nonexistent/card-agents.yaml"), **extra: Any
) -> Settings:
    return Settings(
        database_url=SecretStr(database_url),
        hfm_e2e=True,
        card_agents_file=registry,
        budget_config=REPO_CONFIG / "budget.yaml",
        google_client_id=CLIENT_ID,
        auth_public_key_file=public_key,
        **extra,
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(deps=app_deps(scripted()))) as entered:
        yield entered


def test_health_is_static(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_is_503_when_the_database_fails(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}


async def test_ready_runs_select_one_against_the_database(pg_url: str) -> None:
    engine = build_engine(pg_url)
    try:
        app = create_app(deps=app_deps(scripted(), sessions=session_factory(engine)))
        with TestClient(app) as client:
            response = client.get("/ready")
    finally:
        await engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_dist_is_served_at_root_without_shadowing_the_api(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>review</html>")
    app = create_app(settings(hfm_frontend_dist=tmp_path), deps=app_deps(scripted()))
    with TestClient(app) as client:
        assert client.get("/").text == "<html>review</html>"
        assert client.get("/health").json() == {"status": "ok"}


def test_frontend_dist_without_index_fails_startup_naming_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=str(tmp_path)):
        create_app(settings(hfm_frontend_dist=tmp_path), deps=app_deps(scripted()))


@pytest.mark.usefixtures("restore_logging")
def test_production_wiring_records_a_failed_review_in_postgres(
    pg_url: str, public_key: Path, registry: Path
) -> None:
    """The canned report and a card agent nobody listens on: the review fails at discovery. The
    person signs in with a token the configured public key verifies."""
    with TestClient(create_app(settings(pg_url, public_key, registry))) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        signed_in = client.post("/api/auth/session", json={"credential": sign()})
        assert signed_in.json()["email"] == "dana@example.com"
        review_id = client.post("/api/reviews", json={"month": MONTH}).json()["id"]
        app = client.app
        assert isinstance(app, FastAPI)
        runner: ReviewRunner = app.state.runner
        assert client.portal is not None
        client.portal.call(runner.drain)

        assert client.get(f"/api/reviews/{review_id}").json()["status"] == "failed"
        events = client.portal.call(app.state.deps.events.list, review_id)
    assert [event.type for _, event in events] == [REVIEW_FAILED]


@pytest.mark.usefixtures("restore_logging")
async def test_startup_fails_a_review_a_stopped_server_left_running(
    pg_url: str, public_key: Path
) -> None:
    engine = build_engine(pg_url)
    try:
        stamp = datetime(2026, 10, 1, tzinfo=UTC)
        await PostgresReviewRepository(session_factory(engine)).add(
            Review("r-interrupted", DANA.id, OTHER_MONTH, ReviewStatus.RUNNING, stamp)
        )
    finally:
        await engine.dispose()

    with TestClient(create_app(settings(pg_url, public_key))) as client:
        client.cookies.set(COOKIE, sign())
        view = client.get("/api/reviews/r-interrupted").json()
        app = client.app
        assert isinstance(app, FastAPI)
        assert client.portal is not None
        events = client.portal.call(app.state.deps.events.list, "r-interrupted")
    assert view["status"] == "failed"
    [(seq, event)] = events
    assert (seq, event.type, event.data["message"]) == (1, REVIEW_FAILED, INTERRUPTED_MESSAGE)
    datetime.fromisoformat(event.data["at"])
