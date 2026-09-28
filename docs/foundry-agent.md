# Connect a Foundry agent to the MCP server

The Foundry project, model deployment and the server's Entra app registration are
created by Terraform. The agent and its MCP tool connection are data-plane
configuration, set up once per environment.

## 1. Give the agent an identity the server trusts

The server accepts app-only tokens whose `roles` claim contains `dms.read` and
`dms.write`. It never grants `dms.manager` to an application.

* **Project managed identity** (all agents in the project share it): take
  `foundry_project_principal_id` from `terraform output` and add it to
  `foundry_agent_principal_ids` in the environment stack, then apply.
* **Agent identity** (one identity per published agent, recommended for least
  privilege): after publishing the agent, add its service principal object ID to
  `foundry_agent_principal_ids` instead.

## 2. Add the MCP tool to the agent

Portal: Foundry project > Build > your agent > Tools > Add > Custom >
Model Context Protocol, then:

| Field | Value |
| --- | --- |
| Remote MCP Server endpoint | `terraform output -raw mcp_url` |
| Authentication | Microsoft Entra |
| Type | Agent identity (or Project managed identity) |
| Audience | the `entra_client_id` output (the token audience) |

CLI alternative:

```bash
azd ai project set "<project endpoint>"
azd ai connection create dealer-mcp \
  --kind remote-tool \
  --target "$(terraform output -raw mcp_url)" \
  --auth-type agentic-identity \
  --audience "<entra_client_id>"
```

## 3. Keep approvals on

In the agent's MCP tool settings keep `require_approval` at `always` for write
tools (or list only read tools under `never`). Restrict `allowed_tools` to the
tools the agent needs. The server enforces permissions regardless; these
settings add a second, client-side layer.

References: [Connect agents to MCP servers](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol),
[MCP tool authentication](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication).
