"""Authentication and visibility: who can connect, and what each caller can see."""

import httpx
import pytest
from conftest import token

READ_TOOLS = {
    "search_inventory",
    "get_vehicle",
    "quote_price",
    "estimate_payment",
    "check_test_drive_slots",
}
WRITE_TOOLS = {"create_lead", "get_lead", "book_test_drive", "apply_discount"}
MANAGER_TOOLS = {"mark_vehicle_sold", "delete_lead"}


def _post(url, tok=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    return httpx.post(f"{url}/mcp", json=body, headers=headers)


def test_no_token_is_401_with_resource_metadata(server):
    r = _post(server.url)
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers["www-authenticate"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"audience": "https://graph.microsoft.com"},  # token for another API: no passthrough
        {"issuer": "https://evil.example.com"},
        {"expires_in_seconds": -60},
    ],
    ids=["wrong_audience", "wrong_issuer", "expired"],
)
def test_bad_tokens_rejected(server, keys, overrides):
    assert _post(server.url, token(keys, "salesperson", **overrides)).status_code == 401


def test_token_signed_by_another_key_rejected(server):
    from fastmcp.server.auth.providers.jwt import RSAKeyPair

    from server import devtoken

    forged = RSAKeyPair.generate().create_token(
        issuer=devtoken.ISSUER, audience=devtoken.AUDIENCE, additional_claims={"scp": "dms.manager"}
    )
    assert _post(server.url, forged).status_code == 401


def test_protected_resource_metadata(server):
    r = httpx.get(f"{server.url}/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    body = r.json()
    assert body["authorization_servers"] == ["https://dev.local/dealer-mcp"]
    # Least privilege: only the baseline scope is advertised up front.
    assert body["scopes_supported"] == ["dms.read"]


def test_healthz_is_public(server):
    assert httpx.get(f"{server.url}/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("persona", "expected"),
    [
        ("readonly", READ_TOOLS),
        ("salesperson", READ_TOOLS | WRITE_TOOLS),
        ("agent", READ_TOOLS | WRITE_TOOLS),  # app roles work like scopes, never manager
        ("manager", READ_TOOLS | WRITE_TOOLS | MANAGER_TOOLS),
    ],
)
async def test_tools_visible_per_persona(connect, persona, expected):
    async with connect(persona) as c:
        assert {t.name for t in await c.list_tools()} == expected


async def test_unknown_permission_values_are_ignored(connect, keys):
    # A token carrying a role this server does not define gains nothing.
    tok = token(
        keys, "readonly", additional_claims={"oid": "x", "scp": "dms.read", "roles": ["admin", "*"]}
    )
    async with connect(raw_token=tok) as c:
        assert {t.name for t in await c.list_tools()} == READ_TOOLS


async def test_hidden_tool_cannot_be_called(connect):
    async with connect("salesperson") as c:
        with pytest.raises(Exception) as exc:
            await c.call_tool("delete_lead", {"lead_id": "L-0000000000000000"})
        # A step-up signal naming only the missing scope, never the full catalog.
        assert "insufficient scope" in str(exc.value)
        assert "dms.manager" in str(exc.value) and "dms.write" not in str(exc.value)
