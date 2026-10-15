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
from hfm.platform.app import create_app
from hfm.platform.config import Settings
from hfm.platform.db import build_engine, session_factory
from hfm.platform.review_runner import INTERRUPTED_MESSAGE, ReviewRunner
from tests.platform.support import MONTH, OTHER_MONTH, app_deps, scripted

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config"


UNREACHABLE_DATABASE = "postgresql+psycopg://u:p@127.0.0.1:1/d"


def settings(database_url: str = UNREACHABLE_DATABASE, **extra: Any) -> Settings:
    return Settings(
        database_url=SecretStr(database_url),
        hfm_e2e=True,
        amex_agent_token=SecretStr("token"),
        amex_agent_url="http://127.0.0.1:1",
        agents_config=REPO_CONFIG / "agents.yaml",
        budget_config=REPO_CONFIG / "budget.yaml",
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
def test_production_wiring_records_a_failed_review_in_postgres(pg_url: str) -> None:
    """The canned report and an Amex URL nobody listens on: the review fails at discovery."""
    with TestClient(create_app(settings(pg_url))) as client:
        assert client.get("/ready").status_code == 200
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
async def test_startup_fails_a_review_a_stopped_server_left_running(pg_url: str) -> None:
    engine = build_engine(pg_url)
    try:
        stamp = datetime(2026, 10, 1, tzinfo=UTC)
        await PostgresReviewRepository(session_factory(engine)).add(
            Review("r-interrupted", OTHER_MONTH, ReviewStatus.RUNNING, stamp)
        )
    finally:
        await engine.dispose()

    with TestClient(create_app(settings(pg_url))) as client:
        view = client.get("/api/reviews/r-interrupted").json()
        app = client.app
        assert isinstance(app, FastAPI)
        assert client.portal is not None
        events = client.portal.call(app.state.deps.events.list, "r-interrupted")
    assert view["status"] == "failed"
    [(seq, event)] = events
    assert (seq, event.type, event.data["message"]) == (1, REVIEW_FAILED, INTERRUPTED_MESSAGE)
    datetime.fromisoformat(event.data["at"])
