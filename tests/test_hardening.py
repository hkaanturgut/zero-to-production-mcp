"""Production hardening: Origin validation and confirmations across replicas."""

from dataclasses import replace

import httpx
import httpx2
import pytest
from conftest import _serve, always_yes, token
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import MCPError

from dms import app as dms_app
from server.backend.mock_client import CircuitBreaker

SHARED_KEY = "k" * 32


def test_foreign_origin_is_rejected(server):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    evil = httpx.post(f"{server.url}/mcp", json=body, headers={"Origin": "https://evil.example"})
    same = httpx.post(f"{server.url}/mcp", json=body, headers={"Origin": server.url})
    none = httpx.post(f"{server.url}/mcp", json=body)
    assert evil.status_code == 403
    assert same.status_code == 401 and none.status_code == 401  # reach auth, no token


def _two_replicas(settings, keys: tuple[str, ...]):
    s = replace(settings, rate_limit_rps=1000, rate_limit_burst=1000, request_state_keys=keys)
    return (_serve(s, breaker=CircuitBreaker(threshold=1000)) for _ in range(2))


def _load_balanced(a, b, tok):
    """A client whose confirmation round trip lands on a different replica."""

    class Router(httpx2.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            target = b if b"inputResponses" in request.content else a
            port = int(target.url.rsplit(":", 1)[1])
            request.url = request.url.copy_with(port=port)
            return await super().handle_async_request(request)

    def factory(**kw):
        return httpx2.AsyncClient(**kw, transport=Router())

    transport = StreamableHttpTransport(f"{a.url}/mcp", httpx_client_factory=factory)
    return Client(transport, auth=BearerAuth(tok), elicitation_handler=always_yes)


ARGS = {"stock_number": "TBA-1001", "amount": 900, "reason": "loyal"}


async def test_confirmation_survives_another_replica_with_shared_key(settings, keys):
    a, b = _two_replicas(settings, (SHARED_KEY,))
    async with _load_balanced(a, b, token(keys, "manager")) as c:
        r = await c.call_tool("apply_discount", ARGS)
    assert r.structured_content["discount"] == 900


async def test_confirmation_fails_closed_across_replicas_without_shared_key(settings, keys):
    a, b = _two_replicas(settings, ())
    async with _load_balanced(a, b, token(keys, "manager")) as c:
        with pytest.raises(MCPError, match="requestState"):  # rejected by the SDK
            await c.call_tool("apply_discount", ARGS)
    assert dms_app.State.store.vehicles["TBA-1001"].discount == 0
