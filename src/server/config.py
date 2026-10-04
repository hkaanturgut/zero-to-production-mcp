"""Runtime configuration, read once from the environment.

Secrets (the DMS API key) come from the environment only. In Azure the
Container App injects them from Key Vault through its managed identity, so they
never appear in code, images, Bicep deployment outputs or tool results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Settings:
    dms_base_url: str
    dms_api_key: str = field(repr=False)  # never printed, even in debug logs
    auth_mode: Literal["entra", "local"]
    public_base_url: str
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_api_uri: str | None = None  # Application ID URI; scopes are <uri>/dms.read
    local_issuer: str = "https://dev.local/dealer-mcp"
    local_audience: str = "api://dealer-mcp-dev"
    local_public_key_path: str = ".dev/jwt_public.pem"
    discount_limit: float = 500.0
    max_discount_ratio: float = 0.15
    rate_limit_rps: float = 5.0
    rate_limit_burst: int = 20
    dms_timeout_s: float = 1.5  # per attempt; 3 read attempts stay under 5 s
    # Keys that seal the multi round-trip requestState. Share them across
    # replicas, or a confirmation answered on another replica fails closed.
    # First key seals, all keys unseal: rotate as [new, old], then [new].
    request_state_keys: tuple[str, ...] = field(default=(), repr=False)
    # Browser origins allowed to call /mcp. Empty: only PUBLIC_BASE_URL.
    allowed_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> Settings:
        mode = os.environ.get("AUTH_MODE", "local")
        if mode not in ("entra", "local"):
            raise ValueError("AUTH_MODE must be 'entra' or 'local'")
        key = os.environ.get("DMS_API_KEY")
        if not key:
            raise ValueError("DMS_API_KEY must be set")
        s = cls(
            dms_base_url=os.environ.get("DMS_BASE_URL", "http://127.0.0.1:8081"),
            dms_api_key=key,
            auth_mode=mode,  # type: ignore[arg-type]
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8080"),
            entra_tenant_id=os.environ.get("ENTRA_TENANT_ID"),
            entra_client_id=os.environ.get("ENTRA_CLIENT_ID"),
            entra_api_uri=os.environ.get("ENTRA_API_URI"),
            local_public_key_path=os.environ.get("LOCAL_JWT_PUBLIC_KEY", ".dev/jwt_public.pem"),
            discount_limit=float(os.environ.get("DISCOUNT_LIMIT", "500")),
            request_state_keys=_csv("REQUEST_STATE_KEYS"),
            allowed_origins=_csv("ALLOWED_ORIGINS"),
        )
        if s.auth_mode == "entra" and not (s.entra_tenant_id and s.entra_client_id):
            raise ValueError("ENTRA_TENANT_ID and ENTRA_CLIENT_ID are required in entra mode")
        return s


def _csv(name: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in os.environ.get(name, "").split(",") if v.strip())
