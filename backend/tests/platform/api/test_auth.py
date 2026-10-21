"""Sign-in: the posted credential becomes a cookie that lasts as long as the token, protected
routes need it, and signing out drops it."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

from fastapi.testclient import TestClient

from hfm.platform.api.auth import COOKIE
from hfm.platform.app import create_app
from tests.fakes import FakeTokenVerifier
from tests.platform.support import DANA, DANA_TOKEN, MONTH, TOKENS, app_deps, scripted


def set_cookie(response) -> SimpleCookie:
    jar = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    return jar


def test_the_client_id_is_public() -> None:
    with TestClient(create_app(deps=app_deps(scripted()))) as client:
        assert client.get("/api/auth/config").json() == {"clientId": "hfm-test-client"}


def test_sign_in_sets_a_cookie_that_lasts_as_long_as_the_token() -> None:
    deps = app_deps(scripted())
    expires_at = datetime.now(UTC) + timedelta(minutes=50)
    deps = deps.__class__(**{**deps.__dict__, "verifier": FakeTokenVerifier(TOKENS, expires_at)})
    with TestClient(create_app(deps=deps)) as client:
        response = client.post("/api/auth/session", json={"credential": DANA_TOKEN})
        assert response.status_code == 200
        assert response.json() == {"id": DANA.id, "email": DANA.email, "name": DANA.name}
        cookie = set_cookie(response)[COOKIE]
        assert cookie.value == DANA_TOKEN
        assert cookie["httponly"]
        assert cookie["samesite"].lower() == "strict"
        assert cookie["path"] == "/"
        assert not cookie["secure"], "the test client speaks plain http"
        assert 49 * 60 < int(cookie["max-age"]) <= 50 * 60

        assert client.get("/api/auth/me").json()["id"] == DANA.id
        assert client.get(f"/api/months/{MONTH}").status_code == 200


def test_the_cookie_is_secure_over_https() -> None:
    with TestClient(create_app(deps=app_deps(scripted())), base_url="https://hfm.test") as client:
        response = client.post("/api/auth/session", json={"credential": DANA_TOKEN})
        assert set_cookie(response)[COOKIE]["secure"]


def test_a_bad_credential_is_401_with_the_reason_and_sets_no_cookie() -> None:
    with TestClient(create_app(deps=app_deps(scripted()))) as client:
        response = client.post("/api/auth/session", json={"credential": "forged"})
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert "not valid" in response.json()["detail"]
        assert "set-cookie" not in response.headers


def test_protected_routes_are_401_without_a_valid_cookie() -> None:
    with TestClient(create_app(deps=app_deps(scripted()))) as client:
        for path in ("/api/auth/me", f"/api/months/{MONTH}", "/api/reviews/r1",
                     "/api/reviews/r1/events"):
            response = client.get(path)
            assert response.status_code == 401, path
            assert response.json() == {"detail": "sign in to continue"}
            assert response.headers["WWW-Authenticate"] == "Bearer"
        assert client.post("/api/reviews", json={"month": MONTH}).status_code == 401
        client.cookies.set(COOKIE, "stale-token")
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        assert "not valid" in response.json()["detail"]
        assert client.get("/health").status_code == 200


def test_sign_out_drops_the_cookie() -> None:
    with TestClient(create_app(deps=app_deps(scripted()))) as client:
        client.post("/api/auth/session", json={"credential": DANA_TOKEN})
        response = client.delete("/api/auth/session")
        assert response.status_code == 204
        assert set_cookie(response)[COOKIE]["max-age"] == "0"
        assert client.get("/api/auth/me").status_code == 401
