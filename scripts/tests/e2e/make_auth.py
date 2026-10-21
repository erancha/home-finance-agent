#!/usr/bin/env python3
"""Write what the end-to-end stack needs to connect its agents and verify sign-ins without Google.

Into the mounted folder: the public key both agents verify tokens with (auth-public.pem),
amex-agent's callers file registering the manager under a throwaway secret (allowed-callers.yaml),
and the manager's registry connecting it to amex-agent at its compose service address with that
secret (card-agents.yaml). Into the private folder: the key run_review.py signs its tokens with
(auth-private.pem). The issuer and client ids match docker-compose.e2e.yml.

    backend/.venv/bin/python scripts/tests/e2e/make_auth.py <mounted folder> <private folder>
"""
from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SECRET = "hfm-e2e-secret"
AGENT_URL = "http://amex-agent:8020"
"""The compose service address; amex-agent's APP_AGENT_URL in docker-compose.e2e.yml equals it."""

CALLERS = f"""\
app:
  a2a:
    allowed_callers:
      - name: home-finance-agent
        shared_secret: {SECRET}
        client_id: hfm-e2e-client
"""
CARD_AGENTS = f"""\
agents:
  - name: amex
    url: {AGENT_URL}
    browser_url: http://localhost:8020
    shared_secret: {SECRET}
"""


def main(mounted: Path, private: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (private / "auth-private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public = mounted / "auth-public.pem"
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    callers = mounted / "allowed-callers.yaml"
    callers.write_text(CALLERS)
    registry = mounted / "card-agents.yaml"
    registry.write_text(CARD_AGENTS)
    # The same mode add-card-agent.sh and register-caller.sh give the real files.
    for file in (callers, registry):
        file.chmod(0o600)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
