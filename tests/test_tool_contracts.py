"""Guardrails on the tool surface itself. A new tool that forgets them fails CI."""

from conftest import token


async def test_every_tool_is_documented_annotated_and_typed(connect):
    async with connect("manager") as c:
        tools = await c.list_tools()
    assert len(tools) == 11
    for t in tools:
        assert t.description and len(t.description) >= 40, f"{t.name}: describe it for the model"
        assert t.annotations is not None, f"{t.name}: missing annotations"
        assert t.output_schema, f"{t.name}: missing output schema"
        assert t.input_schema.get("additionalProperties") is not True, t.name


def test_every_tool_has_exactly_one_permission_tag(settings, keys):
    # Fail closed: an untagged tool would be callable by any authenticated caller.
    import asyncio

    from server.app import TAG_PERMISSIONS, build_server

    mcp = build_server(settings)
    tools = asyncio.run(mcp.list_tools(run_middleware=False))
    assert len(tools) == 11
    for t in tools:
        assert len(t.tags & set(TAG_PERMISSIONS)) == 1, f"{t.name} tags={t.tags}"
    _ = token  # keep fixture import used
