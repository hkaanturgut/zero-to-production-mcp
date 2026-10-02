"""Mint local test tokens for offline development and the workshop fallback.

    uv run dev-token salesperson   # dms.read dms.write, a user token
    uv run dev-token manager       # adds dms.manager
    uv run dev-token agent         # app-only token with roles, like a Foundry agent

The first run creates an RSA key pair in .dev/ (git-ignored). The server in
AUTH_MODE=local trusts only that public key, issuer and audience.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastmcp.server.auth.providers.jwt import RSAKeyPair
from pydantic import SecretStr

DEV_DIR = Path(".dev")
ISSUER = "https://dev.local/dealer-mcp"
AUDIENCE = "api://dealer-mcp-dev"

PERSONAS = {
    "salesperson": {
        "sub": "demo-salesperson",
        "claims": {
            "oid": "demo-salesperson",
            "name": "Sam Sales",
            "idtyp": "user",
            "scp": "dms.read dms.write",
        },
    },
    "manager": {
        "sub": "demo-manager",
        "claims": {
            "oid": "demo-manager",
            "name": "Maya Manager",
            "idtyp": "user",
            "scp": "dms.read dms.write dms.manager",
        },
    },
    "agent": {
        "sub": "demo-foundry-agent",
        "claims": {
            "oid": "demo-foundry-agent",
            "azp": "foundry-sales-agent",
            "idtyp": "app",
            "roles": ["dms.agent.read", "dms.agent.write"],
        },
    },
    "readonly": {
        "sub": "demo-viewer",
        "claims": {"oid": "demo-viewer", "name": "Vic Viewer", "idtyp": "user", "scp": "dms.read"},
    },
}


def load_or_create_keys() -> RSAKeyPair:
    DEV_DIR.mkdir(exist_ok=True)
    priv, pub = DEV_DIR / "jwt_private.pem", DEV_DIR / "jwt_public.pem"
    if priv.exists() and pub.exists():
        return RSAKeyPair(private_key=SecretStr(priv.read_text()), public_key=pub.read_text())
    kp = RSAKeyPair.generate()
    priv.write_text(kp.private_key.get_secret_value())
    priv.chmod(0o600)
    pub.write_text(kp.public_key)
    return kp


def mint(persona: str, keys: RSAKeyPair, expires_in_seconds: int = 8 * 3600) -> str:
    p = PERSONAS[persona]
    return keys.create_token(
        subject=p["sub"],
        issuer=ISSUER,
        audience=AUDIENCE,
        expires_in_seconds=expires_in_seconds,
        additional_claims=p["claims"],
    )


def main() -> None:
    persona = sys.argv[1] if len(sys.argv) > 1 else "salesperson"
    if persona not in PERSONAS:
        sys.exit(f"persona must be one of: {', '.join(PERSONAS)}")
    print(mint(persona, load_or_create_keys()))


if __name__ == "__main__":
    main()
