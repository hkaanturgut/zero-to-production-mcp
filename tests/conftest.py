"""Test harness: real HTTP, real auth, in-process mock DMS.

The MCP server runs under uvicorn on a free port with local JWT auth. The DMS
runs in-process behind httpx's ASGI transport, so tests are fast and offline
but exercise the same code paths as production.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server.auth.providers.jwt import RSAKeyPair

DMS_KEY = "test-dms-key-" + "x" * 24
os.environ["DMS_API_KEY"] = DMS_KEY

from dms import app as dms_app  # noqa: E402
from dms.seed import build_store  # noqa: E402
from server import devtoken  # noqa: E402
from server.app import build_app  # noqa: E402
from server.backend.mock_client import CircuitBreaker, MockDmsClient  # noqa: E402
from server.config import Settings  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def keys(tmp_path_factory) -> RSAKeyPair:
    return RSAKeyPair.generate()


@pytest.fixture(scope="session")
def settings(keys, tmp_path_factory) -> Settings:
    pub = Path(tmp_path_factory.mktemp("keys")) / "pub.pem"
    pub.write_text(keys.public_key)
    return Settings(
        dms_base_url="http://dms",
        dms_api_key=DMS_KEY,
        auth_mode="local",
        public_base_url="http://127.0.0.1",
        local_public_key_path=str(pub),
        dms_timeout_s=0.5,
    )


class Running:
    def __init__(self, url: str, backend: MockDmsClient):
        self.url = url
        self.backend = backend


def _serve(settings: Settings, **backend_kw) -> Running:
    port = _free_port()
    settings = replace(settings, public_base_url=f"http://127.0.0.1:{port}")
    backend = MockDmsClient(
        settings.dms_base_url,
        settings.dms_api_key,
        timeout_s=settings.dms_timeout_s,
        transport=httpx.ASGITransport(app=dms_app.app),
        **backend_kw,
    )
    app = build_app(settings, backend)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return Running(f"http://127.0.0.1:{port}", backend)


@pytest.fixture(scope="session")
def server(settings) -> Running:
    return _serve(
        replace(settings, rate_limit_rps=1000, rate_limit_burst=1000),
        breaker=CircuitBreaker(threshold=1000),
    )


@pytest.fixture(scope="session")
def limited_server(settings) -> Running:
    return _serve(replace(settings, rate_limit_rps=0.1, rate_limit_burst=3))


@pytest.fixture(autouse=True)
def fresh_dms():
    dms_app.State.store = build_store()
    dms_app.State.chaos = "off"
    yield
    dms_app.State.chaos = "off"


def token(keys: RSAKeyPair, persona: str, **overrides) -> str:
    p = devtoken.PERSONAS[persona]
    kw = {
        "subject": p["sub"],
        "issuer": devtoken.ISSUER,
        "audience": devtoken.AUDIENCE,
        "additional_claims": p["claims"],
    }
    kw.update(overrides)
    return keys.create_token(**kw)


@pytest.fixture
def connect(server, keys):
    """connect("manager") -> an MCP client for that persona."""

    def _connect(persona: str = "salesperson", *, elicit=None, url=None, raw_token=None):
        tok = raw_token or token(keys, persona)
        return Client(
            f"{url or server.url}/mcp",
            auth=BearerAuth(tok),
            elicitation_handler=elicit,
        )

    return _connect


async def always_yes(message, response_type, params, context):
    return {"confirm": True}


async def always_no(message, response_type, params, context):
    return {"confirm": False}
