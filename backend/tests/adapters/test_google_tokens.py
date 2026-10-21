"""Token verification against the test key pair, so no test reaches Google."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWKClient

from hfm.adapters.google_tokens import (
    GOOGLE_ISSUER,
    GoogleTokenVerifier,
    JwksKeys,
    StaticKey,
)
from hfm.domain.errors import InvalidTokenError
from hfm.domain.models import User
from tests.auth_keys import CLIENT_ID, KID, OTHER_KEY, PRIVATE_KEY, PUBLIC_PEM, sign


def verifier(issuer: str = GOOGLE_ISSUER) -> GoogleTokenVerifier:
    return GoogleTokenVerifier(CLIENT_ID, issuer, StaticKey(PUBLIC_PEM))


def test_a_valid_token_names_the_person_and_its_expiry() -> None:
    now = int(time.time())
    verified = verifier().verify(sign(exp=now + 60))
    assert verified.user == User("1001", "dana@example.com", "Dana")
    assert int(verified.expires_at.timestamp()) == now + 60


def test_email_and_name_are_optional() -> None:
    token = sign()
    payload = jwt.decode(token, options={"verify_signature": False})
    del payload["email"], payload["name"]
    bare = jwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})
    assert verifier().verify(bare).user == User("1001", None, None)


def test_google_bare_issuer_form_is_accepted_for_google_only() -> None:
    assert verifier().verify(sign(iss="accounts.google.com")).user.id == "1001"
    with pytest.raises(InvalidTokenError, match="not issued by hfm-e2e"):
        verifier("hfm-e2e").verify(sign(iss="accounts.google.com"))


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"exp": int(time.time()) - 1}, "expired"),
        ({"aud": "other-client"}, "another application"),
        ({"iss": "https://evil.example"}, "not issued by"),
    ],
)
def test_wrong_claims_are_refused_with_a_reason(claims: dict[str, Any], reason: str) -> None:
    with pytest.raises(InvalidTokenError, match=reason):
        verifier().verify(sign(**claims))


def test_a_token_signed_by_another_key_is_refused() -> None:
    with pytest.raises(InvalidTokenError, match="not valid"):
        verifier().verify(sign(key=OTHER_KEY))


def test_unsigned_and_symmetric_tokens_are_refused() -> None:
    payload = jwt.decode(sign(), options={"verify_signature": False})
    for token in (
        jwt.encode(payload, None, algorithm="none"),
        jwt.encode(payload, "s" * 32, algorithm="HS256"),
        "not.a.token",
    ):
        with pytest.raises(InvalidTokenError, match="not valid"):
            verifier().verify(token)


def test_a_token_missing_a_required_claim_is_refused() -> None:
    payload = jwt.decode(sign(), options={"verify_signature": False})
    del payload["sub"]
    token = jwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})
    with pytest.raises(InvalidTokenError, match="not valid"):
        verifier().verify(token)


def test_static_key_reads_a_pem_file_and_refuses_a_non_rsa_key(tmp_path: Path) -> None:
    pem = tmp_path / "public.pem"
    pem.write_bytes(PUBLIC_PEM)
    assert GoogleTokenVerifier(CLIENT_ID, GOOGLE_ISSUER, StaticKey.from_file(pem)).verify(sign())
    ec_pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with pytest.raises(TypeError, match="RSA"):
        StaticKey(ec_pem)


def test_jwks_keys_select_the_signing_key_by_its_id(monkeypatch: pytest.MonkeyPatch) -> None:
    jwk = jwt.PyJWK.from_dict(
        {**jwt.algorithms.RSAAlgorithm.to_jwk(PRIVATE_KEY.public_key(), as_dict=True),
         "kid": KID, "alg": "RS256", "use": "sig"}
    )
    other = jwt.PyJWK.from_dict(
        {**jwt.algorithms.RSAAlgorithm.to_jwk(OTHER_KEY.public_key(), as_dict=True),
         "kid": "key-2", "alg": "RS256", "use": "sig"}
    )
    fetched: list[str] = []

    def fetch_data(self: PyJWKClient) -> dict[str, Any]:
        fetched.append(self.uri)
        return {"keys": [other._jwk_data, jwk._jwk_data]}

    monkeypatch.setattr(PyJWKClient, "fetch_data", fetch_data)
    keys = JwksKeys("https://keys.example/certs")
    checker = GoogleTokenVerifier(CLIENT_ID, GOOGLE_ISSUER, keys)

    assert checker.verify(sign()).user.id == "1001"
    assert checker.verify(sign()).user.id == "1001"
    assert fetched == ["https://keys.example/certs"]
    with pytest.raises(InvalidTokenError, match="not valid"):
        checker.verify(jwt.encode(
            jwt.decode(sign(), options={"verify_signature": False}), OTHER_KEY,
            algorithm="RS256", headers={"kid": "key-3"},
        ))
