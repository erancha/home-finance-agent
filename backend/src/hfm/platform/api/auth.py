"""Sign-in routes and the dependency that names the person behind a request.

The page signs people in with Google and posts the ID token here; the token itself becomes an
HttpOnly cookie that lasts until the token expires, and every protected route verifies it again
on each request. There is no server-side session: the cookie carries the proof, and the browser's
event-stream object, which cannot send headers, carries it too.

Core building blocks:
- Session: the verified person and their token, which a card-agent fetch forwards
- current_session / CurrentSession: the dependency protected routes take; 401 without a valid
  cookie
- router: /api/auth/config (the public client id), /api/auth/session (sign in, sign out),
  /api/auth/me (who is signed in)
- register_error_handlers: a missing or bad token answers 401 with the reason
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hfm.domain.errors import InvalidTokenError
from hfm.domain.models import User, VerifiedToken
from hfm.platform.dependencies import Deps

COOKIE = "hfm_id_token"
NOT_SIGNED_IN = "sign in to continue"

router = APIRouter(prefix="/api/auth")


class NotSignedInError(Exception):
    """The request carries no token at all."""


@dataclass(frozen=True)
class Session:
    user: User
    token: str
    """The ID token as the browser sent it; a fetch from a card agent forwards it unchanged."""


def current_session(request: Request, deps: Deps) -> Session:
    # The cookie is absent on a first visit and after sign-out: a legal state, answered 401.
    token = request.cookies.get(COOKIE)
    if token is None:
        raise NotSignedInError(NOT_SIGNED_IN)
    return Session(deps.verifier.verify(token).user, token)


CurrentSession = Annotated[Session, Depends(current_session)]


class ConfigResponse(BaseModel):
    client_id: str


class CredentialRequest(BaseModel):
    credential: str
    """The ID token Google's sign-in button hands the page."""


class UserResponse(BaseModel):
    id: str
    email: str | None
    name: str | None

    @classmethod
    def of(cls, user: User) -> UserResponse:
        return cls(id=user.id, email=user.email, name=user.name)


@router.get("/config")
async def config(deps: Deps) -> dict[str, str]:
    return {"clientId": deps.google_client_id}


@router.post("/session")
async def sign_in(
    body: CredentialRequest, request: Request, response: Response, deps: Deps
) -> UserResponse:
    verified = deps.verifier.verify(body.credential)
    set_session_cookie(response, request, body.credential, verified)
    return UserResponse.of(verified.user)


@router.get("/me")
async def me(session: CurrentSession) -> UserResponse:
    return UserResponse.of(session.user)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(response: Response) -> Response:
    response.delete_cookie(COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def set_session_cookie(
    response: Response, request: Request, token: str, verified: VerifiedToken
) -> None:
    """The cookie lives exactly as long as the token: once it expires, the next request is 401 and
    the page asks the person to sign in again."""
    remaining = int((verified.expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        COOKIE,
        token,
        max_age=max(remaining, 0),
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def register_error_handlers(app: FastAPI) -> None:
    async def unauthorized(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, InvalidTokenError | NotSignedInError)
        return JSONResponse(
            {"detail": str(error)},
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.add_exception_handler(InvalidTokenError, unauthorized)
    app.add_exception_handler(NotSignedInError, unauthorized)
