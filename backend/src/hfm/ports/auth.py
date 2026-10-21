"""Port to the identity provider: turns an ID token into the person it describes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hfm.domain.models import VerifiedToken


@runtime_checkable
class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedToken:
        """Return the person a valid token describes and when it expires; raises
        InvalidTokenError otherwise."""
        ...
