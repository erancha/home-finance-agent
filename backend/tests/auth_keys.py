"""A key pair generated at import, and tokens signed with it, so no test reaches Google."""
from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from hfm.adapters.google_tokens import GOOGLE_ISSUER

CLIENT_ID = "123-abc.apps.googleusercontent.com"
KID = "key-1"

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)


def sign(key: rsa.RSAPrivateKey = PRIVATE_KEY, **claims: Any) -> str:
    """A token for Dana, valid an hour, with any claim overridden."""
    now = int(time.time())
    payload = {
        "iss": GOOGLE_ISSUER, "aud": CLIENT_ID, "sub": "1001", "iat": now, "exp": now + 3600,
        "email": "dana@example.com", "name": "Dana",
    }
    payload.update(claims)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": KID})
