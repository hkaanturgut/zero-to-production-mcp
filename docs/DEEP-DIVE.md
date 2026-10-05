# Deep dive: Zero to Production MCP

The full reference behind the [README](../README.md): every practice with where the repo implements
it and the official source, plus operations, enterprise questions and lessons learned.

**Contents:** [1. MCP in five minutes](#1-mcp-in-five-minutes) · [2. Architecture](#2-architecture) ·
[3. The tools](#3-the-tools) · [4. Security](#4-security) · [5. Development](#5-development) ·
[6. Operations](#6-operations-and-maintenance) · [7. Scalability](#7-scalability-and-reliability) ·
[8. Observability](#8-observability-and-traceability) · [9. Enterprise questions](#9-enterprise-questions-answered) ·
[10. Lessons](#10-ai-engineering-lessons)

---

## 1. MCP in five minutes

The [Model Context Protocol](https://modelcontextprotocol.io/specification/2026-07-28) is an
open standard for connecting AI applications to tools and data. It uses JSON-RPC 2.0 and
three roles ([architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture)):

| Role | What it is | Here |
| --- | --- | --- |
| **Host** | The AI application the user talks to | VS Code + GitHub Copilot, Claude Code, a Foundry agent |
| **Client** | A connector inside the host, one per server | Built into each host |
| **Server** | A program that exposes capabilities | This repo: `src/server` (reference) and `src/live/server.py` (built on stage) |

A server can offer three kinds of capability:

- **Tools**: functions the model can call (`search_inventory`, `apply_discount`). This server uses tools only.
- **Resources**: data the host can read, such as files or records.
- **Prompts**: reusable prompt templates the user picks.

**What "JSON-RPC 2.0" means.** [JSON-RPC 2.0](https://www.jsonrpc.org/specification) is a tiny standard
for calling a function on another machine with JSON. A request names a `method` and its `params`, and
carries an `id`; the reply echoes that `id` with either a `result` or an `error`. MCP defines the
methods (`tools/list`, `tools/call`, ...); over Streamable HTTP each one is a `POST /mcp`. Calling one
of this server's tools looks like this:

```json
{"jsonrpc": "2.0", "id": 7, "method": "tools/call",
 "params": {"name": "quote_price", "arguments": {"stock_number": "TBA-1017"}}}
```

```json
{"jsonrpc": "2.0", "id": 7,
 "result": {"structuredContent": {"all_in_price": 20209.5, "...": "..."}, "isError": false}}
```

Two kinds of failure, and the difference matters: a tool that runs but says no (for example, a discount
over the limit) returns a normal `result` with `"isError": true` and a sentence the model can act on; a
broken request (unknown method, malformed JSON) gets a JSON-RPC `error` object with a numeric `code`.

### Why MCP instead of a plain REST API?

**Short answer: MCP doesn't replace your REST API. It sits in front of it.** The dealer system in this
repo is a plain REST API (`src/dms`), and it stays that way. The MCP server (`src/server`) is a thin layer
that turns it into something an AI agent can use safely. REST is how programs talk to your system;
MCP is how AI agents talk to it.

**The problem MCP solves.** A REST API is designed for developers who read the docs, write the client
code and decide when to call each endpoint. An agent has none of that: the model decides at runtime
what to call, with what arguments, and it can be tricked by the data it reads. Handing it your REST API
directly leaves three gaps:

1. **Every AI app needs its own integration.** VS Code, Claude, a Foundry agent and Copilot Studio each
   want tools described their own way, with their own auth glue. N apps × M APIs = N×M integrations.
   With MCP you build one server per API, and every MCP host can use it: N + M.
2. **The API is shaped for code, not for a model.** Raw endpoints return everything (here: the VIN,
   internal status and discount notes, a list price without fees) and leave the business rules to the caller. A model
   will happily do the fee math itself, and get it wrong.
3. **The API trusts its caller.** The DMS uses one shared `X-API-Key`. Giving that key to an agent
   means every agent, and anyone who can talk to it, has full access, and you can't tell who did what.

**Side by side**, with this repo's dealer system:

| Concern | Agent calls the REST API directly | Agent calls the MCP server |
| --- | --- | --- |
| How the agent learns what exists | You paste endpoint docs or an OpenAPI file into each app | `tools/list`: names, descriptions written for the model, input and output schemas, at runtime |
| What a "search" returns | `GET /vehicles`: every field, VIN included, prices before fees | `search_inventory`: 10 results, only what the model needs; `quote_price` adds every fee in code |
| Who the caller is | Whoever holds the shared `X-API-Key` | The person or agent in the Entra token (`oid`), checked on every call |
| What the caller may do | Everything the key allows | Only the tools their permissions allow; the rest are hidden from `tools/list` |
| Business rules | In the prompt, hoping the model follows them | In code: the 15% cap and $500 limit hold even against prompt injection |
| Risky actions | The model just calls `POST /discount` | `InputRequiredResult`: a human confirms in the host's UI first |
| Errors | HTTP status codes the model may not understand | `isError` results in plain language the model can act on ("needs a sales manager") |
| Secrets | The API key travels to every agent | The key stays in Key Vault; agents only ever hold their own short-lived token |
| Audit | Access logs show one shared key | One line per tool call: who, which tool, outcome, correlation ID |
| Signing in | Custom per app | Standard OAuth 2.1: the 401 tells any MCP client where to sign in (Protected Resource Metadata) |

**When plain REST is enough.** One application, your own code calling the API, prompts and tools you
control, nothing to reuse: function calling against your API is fine, and MCP adds little. MCP pays off
when several AI hosts or agents need the same system, when callers have different permissions, or when
you need to prove who did what.

### What changed in spec 2026-07-28

This server targets the [2026-07-28 revision](https://modelcontextprotocol.io/specification/2026-07-28/changelog),
the current version per the [versioning page](https://modelcontextprotocol.io/specification/versioning).

| Change | What it means | Where it shows up here |
| --- | --- | --- |
| **Stateless** | No `initialize` handshake and no sessions. The protocol version travels on every request (`MCP-Protocol-Version` header). | Any replica can answer any request; no sticky sessions. |
| **Multi round-trip requests (MRTR)** | A tool can return `InputRequiredResult`; the client asks the user and retries the same call with the answer and an opaque `requestState`. | Manager discounts and deletes (`confirmation()` in `src/server/tools/common.py`). |
| **Client ID Metadata Documents (CIMD)** | Clients identify themselves with a URL to a metadata document. [Dynamic Client Registration is deprecated](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration) in favour of CIMD; pre-registered clients still come first. | We pre-authorize known clients (VS Code, Azure CLI) in Entra. |
| **Deprecated: Roots, Sampling, Logging** | See the [deprecation registry](https://modelcontextprotocol.io/specification/2026-07-28/deprecated). `logging/setLevel` is removed. | Not used. Logs go to stdout and Log Analytics instead. |

The server still serves 2025-11-25 ("handshake-era") clients: `confirmation()` falls back to
classic `ctx.elicit`. `tests/test_legacy_clients.py` covers both eras.

---

## 2. Architecture

![Solution architecture: agent clients sign in with Microsoft Entra ID and call the MCP server through API Management; the server runs on Azure Container Apps in a private network, calls an internal dealer API with a key from a private Key Vault and audits every call to Log Analytics](architecture.svg)

One request, end to end:

1. **Discover.** A call without a token gets 401 with `resource_metadata`, pointing to the
   [Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728.html), which names Entra and the scopes.
2. **Sign in.** The client gets a v2 token from Entra: delegated scopes for people, app roles for agents.
3. **Call.** `POST /mcp` with the bearer token, through API Management: the only public entry, which applies one rate limit per caller across all replicas. Stateless, so any replica can answer.
4. **Verify.** Signature, issuer and audience are checked; `scp` and `roles` merge into one permission set, and tools the caller can't use are hidden.
5. **Act.** Business rules run in code, then the server calls the internal DMS with its API key. The caller's token never goes downstream.
6. **Secret.** `DMS_API_KEY` is a Key Vault reference resolved by a user-assigned managed identity, over a private endpoint.
7. **Audit.** One JSON line per tool call (correlation ID, tool, argument names, caller) lands in Log Analytics.

| Component | Azure resource | Notes |
| --- | --- | --- |
| Front door | API Management `apim-<env>-*` (Developer tier) | The public MCP URL; per-caller rate limit across replicas; static IP |
| MCP server | Container App `ca-mcp-<env>` | `/mcp` and `/healthz`, accepts only API Management's IP, 1 to 3 replicas |
| Dealer API (mock DMS) | Container App `ca-dms-<env>` | Internal ingress only (404 from the internet), exactly 1 replica (in-memory data) |
| Image | Azure Container Registry (Premium) | One image, two entry points (`APP_ENTRY`); admin user off; apps pull over a private endpoint; public endpoint denied except the region's ACR build service (remote builds) and a CI runner while it pushes |
| Secret | Azure Key Vault (RBAC mode) | `DMS_API_KEY`; public network access off, read over a private endpoint |
| Network | Virtual network + private DNS | Container Apps environment in a delegated subnet; private endpoints for Key Vault and ACR |
| Identity | User-assigned managed identity | Key Vault Secrets User, AcrPull |
| Telemetry | Log Analytics + Application Insights | Console logs and audit lines; optional OpenTelemetry |
| Sign-in | Microsoft Entra app `dealer-mcp-<env>` | 2 scopes, 3 app roles, VS Code and Azure CLI pre-authorized |

Design notes: [docs/HLD.md](HLD.md). Stage runbook: [docs/RUNBOOK.md](RUNBOOK.md). Presenter guide: [docs/PRESENTER.md](PRESENTER.md). Show prep and fallbacks: [docs/SHOW-PREP.md](SHOW-PREP.md).

---

## 3. The tools

The reference build (`src/server`) has 11 tools. The stage build (`src/live/server.py`) grows to
7 of them over the workshop. Every tool has exactly one permission tag; a caller sees only the
tools their permissions allow.

| Tool | Tag → permission | Annotations | Inputs (validated) | Returns | Confirmation | Stage build |
| --- | --- | --- | --- | --- | --- | --- |
| `search_inventory` | read → `dms.read` | read-only, idempotent | make, model, body_type, drivetrain, max_price (1k to 200k), max_km, min_year, page (1 to 20) | `SearchResult`, 10 per page, cheapest first | no | yes |
| `get_vehicle` | read | read-only, idempotent | stock_number (`TBA-` + 4 digits) | `VehicleDetail` | no | yes |
| `quote_price` | read | read-only, idempotent | stock_number | `Quote`: price, every fee, discount, HST | no | yes |
| `estimate_payment` | read | read-only, idempotent | stock_number, term 36 to 84 months, down payment | `PaymentEstimate` | no | |
| `check_test_drive_slots` | read | read-only, idempotent | day (today to +30, not Sunday) | `Slots` | no | |
| `create_lead` | write → `dms.write` | idempotent | first/last name, phone pattern, email, stock_number, note (500 max) | `LeadSummary`, masked | no | yes |
| `get_lead` | write | read-only, idempotent | lead_id (`L-` + 16 hex) | `LeadSummary`, masked; note marked untrusted | no | yes |
| `book_test_drive` | write | idempotent | lead_id, stock_number, slot | `Booking` | no | |
| `apply_discount` | write | destructive | stock_number, amount (>0, max 50k), reason (3 to 200 chars) | `DiscountResult` | above $500 (manager only) | yes |
| `mark_vehicle_sold` | manager → `dms.manager` | destructive | stock_number | `SoldResult` | always | |
| `delete_lead` | manager | destructive | lead_id | `DeleteResult` (soft delete) | always | yes |

| Persona | Token | Sees |
| --- | --- | --- |
| `readonly` | user, `dms.read` | 5 read tools |
| `salesperson` | user, `dms.read dms.write` | 9 tools, discounts up to $500 |
| `agent` | app-only, roles `dms.agent.read dms.agent.write` (like a Foundry agent) | 9 tools, never manager |
| `manager` | user, adds the `dms.manager` role | 11 tools, larger discounts after confirmation |

Design choices worth noticing:

- `get_lead` is read-only but tagged **write**: reading customer PII needs the stronger permission.
- **Annotations are hints, not security.** The [tools spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
  says clients must treat them as untrusted. Enforcement lives in the server (`AuthMiddleware`).
- **Pagination instead of truncation.** Responses are bounded by design, so output schemas stay intact.

---

## 4. Security

Each row is a practice, where this repo implements it, and the official source behind it.

| Practice | How it's done here | Source |
| --- | --- | --- |
| **Validate every token**: signature, issuer, audience, expiry | `EntraVerifier` (FastMCP `JWTVerifier`): v2 issuer `.../v2.0`, `aud` = the app's client ID | [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [Entra access token claims](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference) |
| **Advertise how to sign in** | Protected Resource Metadata at `/.well-known/oauth-protected-resource/mcp`; 401s carry `resource_metadata` | [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html) |
| **No token passthrough** | The caller's token is never sent to the DMS. The server uses its own API key and forwards only the caller's object ID. | [Security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) |
| **Audience-bound tokens** | Scopes live on the identifier URI `api://<tenant>/dealer-mcp-<env>`; tokens for other resources are rejected | [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html), [Expose a web API](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-configure-app-expose-web-apis) |
| **People and agents are different principals** | Delegated scopes (`scp`) for people, app roles (`roles`) for agents, merged through a `ROLES` map. Role values differ from scope values so they can't be confused. | [Add app roles](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps) |
| **Least privilege per tool** | One tag per tool, enforced by `AuthMiddleware` + `restrict_tag`; hidden from `tools/list` when not allowed; checked in CI by `test_tool_contracts.py` | [OWASP LLM06 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) |
| **No manager rights for agents** | `dms.manager` is a User-only role; applications can't hold it | Same |
| **Policy in code, not prompts** | 15% hard cap, $500 limit, manager above that, Decimal math (`domain/policy.py`, `domain/pricing.py`) | [OWASP LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) |
| **Untrusted text is data** | Lead notes are labelled untrusted. Lead `L-760debbb3b70b3a1` contains an injected instruction; the model may read it, but policy still refuses. | Same |
| **Human in the loop** | Destructive or costly actions return `InputRequiredResult`; the answer is checked against the original arguments | [MRTR](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr), [Elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation) |
| **Tamper-proof confirmation state** | The MCP SDK seals `requestState` (AES-256-GCM) and binds it to the caller and request; `confirmation()` also rejects changed arguments | [MRTR](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr) (requestState is attacker-controlled) |
| **Secrets the model never sees** | `DMS_API_KEY` only in Key Vault, read by managed identity; never in arguments, results, errors or logs (`test_backend_secret_never_reaches_the_client`) | [Container Apps secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets), [Key Vault RBAC](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide) |
| **Minimal data out** | Phone shows last 4 digits, email first letter + domain, names shortened (`domain/masking.py`) | [Security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) (scope minimization) |
| **Bind data to the caller** | Lead IDs are random; a salesperson can't read another salesperson's lead (`test_cannot_read_another_salespersons_lead`) | Same (state handle hijacking) |
| **Private backend** | DMS has internal ingress only | [Container Apps ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview) |
| **One front door** | API Management is the only public entry; `ca-mcp` allows just its static IP, so the gateway's rate limit can't be bypassed | [APIM MCP servers](https://learn.microsoft.com/en-us/azure/api-management/mcp-server-overview), [Container Apps IP restrictions](https://learn.microsoft.com/en-us/azure/container-apps/ip-restrictions) |
| **Private secrets and images** | Key Vault public access off; ACR pulled over a private endpoint, its public endpoint firewalled | [Key Vault network security](https://learn.microsoft.com/en-us/azure/key-vault/general/network-security), [ACR private endpoints](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-endpoints) |
| **No secrets in CI** | GitHub OIDC federation; CI identity has Contributor, RBAC Admin limited to two roles, Graph rights only on apps it owns | [GitHub OIDC to Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect), [Workload identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust) |
| **Supply chain** | Actions pinned (Trivy by commit SHA), packages locked (`uv.lock`), image scanned, HIGH/CRITICAL fail the release | [GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc) |

Security tests to read first: `tests/test_auth.py`, `tests/test_policy_and_danger.py`,
`tests/test_resilience_and_safety.py`. The full checklist is in [docs/CHECKLIST.md](CHECKLIST.md).

---

## 5. Development

**Tool design**

- Verb-first names, one job each. Descriptions say what *not* to do ("Never add fees or tax yourself").
- Typed, bounded inputs (Pydantic `Field` limits and patterns). The model gets a schema error before your backend sees bad input.
- Output schemas (`Vehicle`, `SearchResult`, `Quote`) so hosts get `structuredContent`, not prose to parse.
- Expected failures return `isError` results the model can act on ("Discounts over $500 need a sales manager."); protocol errors are for protocol problems. See the [tools spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).
- Business math in code with `Decimal`, never in the model.

**Two FastMCP middlewares we deliberately don't use**

- `ErrorHandlingMiddleware`: it turns tool errors into protocol errors, so the model can't recover.
- `ResponseLimitingMiddleware`: truncation strips output schemas. Bound responses by design instead (pagination).

**Testing**

- 76 tests over real HTTP with real JWTs (`tests/conftest.py` starts the DMS and the server).
- Read tool results through `.structured_content` (`.data` returns objects).
- `tests/test_live_stages.py` runs every workshop stage, so the live build can't drift.
- `./scripts/demo.sh rehearse` runs the 34-step stage runbook end to end.
- [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) for manual checks. Pass `--protocol-era modern`; the default is legacy.

**Swappable backend.** Tools depend on the `DmsBackend` protocol (`src/server/backend/base.py`), not
on the mock. Swap in a real DMS client without touching tool code.

---

## 6. Operations and maintenance

| Topic | Practice here |
| --- | --- |
| **Build once, promote** | One image per commit, scanned once, promoted dev → prod with `az acr import` of the same digest. What you tested is what runs. |
| **Infra as code** | Bicep at subscription scope, deployed by azd. PRs show an `azd provision --preview` what-if. |
| **Environments** | `mcpdev` (every push to main), `mcpshow` (manual run with `prod=true`), `mcprehearse` (hot spare, hand-deployed). |
| **Pinning** | FastMCP `4.0.10`, locked dependencies, actions pinned; base image mirrored into ACR so builds don't depend on Docker Hub. |
| **Scanning** | Trivy on every PR and release; fix by patching, not by disabling the scan (see the Dockerfile's OS upgrade step). |
| **Rollback** | Apps run in single-revision mode. Roll back by deploying the previous image tag (re-run the release on the earlier commit, or `az containerapp update --image`). |
| **Secret rotation** | Rotate `DMS_API_KEY` in the GitHub environment secret and re-provision through CI. Never `azd provision` from a laptop on CI-owned envs (it would generate a new key). |
| **Protocol upgrades** | The spec is versioned by date. Support the new era first, keep a fallback for the old one (as `confirmation()` does), and test both. |
| **Deprecations** | Track the [deprecation registry](https://modelcontextprotocol.io/specification/2026-07-28/deprecated) and avoid deprecated features in new code. |

---

## 7. Scalability and reliability

| Concern | Setting | Why |
| --- | --- | --- |
| **Stateless server** | No sessions (2026-07-28) | Horizontal scale without sticky routing |
| **Replicas** | MCP app 1 to 3, DMS exactly 1 | Min 1 avoids cold starts on stage ([scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)); the mock DMS keeps data in memory |
| **Per-attempt deadline** | `asyncio.timeout(1.5)` around each backend call | httpx timeouts apply per phase, so a slow body can exceed them; this caps the whole attempt |
| **Retries** | Reads: 3 attempts, backoff `0.2 · 2^n` s plus jitter. Writes: 1 attempt. | A blind write retry can double a discount |
| **Idempotency** | Writes carry `Idempotency-Key` = hash(caller, tool, arguments) | An agent retry is safe |
| **Circuit breaker** | Opens after 5 failures, half-open after 30 s | Fail fast instead of piling up on a sick backend |
| **Rate limit** | API Management: 120 calls per minute per caller (`rate-limit-by-key` on the token's `oid`), for all replicas at once. The server adds 5 requests/s per caller, burst 20, per replica. | One runaway agent can't starve the rest, however many replicas run |
| **Health** | `/healthz` probes | Container Apps restarts unhealthy replicas |

Try it live: `./scripts/demo.sh chaos slow|errors|flaky|off` breaks the DMS on purpose.

### From one server to hundreds

This repo is one well-built MCP server. Uber's [MCP Gateway](https://www.uber.com/us/en/blog/designing-mcp-gateway/) (October 2026) shows
what changes when a company runs about 800 MCP servers with 5,000+ tools: the same controls move
to a shared place, so hundreds of teams don't each rebuild them.

| Concern | One server (this repo) | Many servers (Uber's MCP Gateway) |
| --- | --- | --- |
| Front door | API Management in front of one server | A stateless gateway in front of all servers; config pulled from a control plane, applied without restarts |
| Discovery | `tools/list` on one endpoint | A central registry: ownership, discovery and enablement for every server |
| Creating tools | Hand-designed tools over the dealer API | Existing service APIs crawled and wrapped automatically; an LLM drafts the tool descriptions |
| Approving tools | Tools and descriptions are code, reviewed in pull requests; `test_tool_contracts.py` blocks untagged tools | Every tool starts disabled; owners enable it; description changes are reviewed config diffs with rollback |
| Sensitive data | Masked in the server, next to the data model, covered by tests | Redaction built into the gateway |
| Token cost | Bounded outputs, 10 results per page | "Response projection": the agent asks for only the fields it needs |
| Long tool lists | 6 to 11 tools, the full list fits | Gradual discovery (`discover_tools`, `get_tool_schema`, `invoke_tool`) and writing large results to files instead of the context |

The takeaway is the same at both sizes: the hard part is the connective tissue (discovery, identity,
security, reliability), not the model.

---

## 8. Observability and traceability

Every tool call writes one JSON audit line:

```json
{"event": "tool_call", "correlation_id": "465ac6a3...", "tool": "apply_discount",
 "arg_names": ["amount", "reason", "stock_number"], "caller_id": "7871a41e-...",
 "caller_kind": "user", "permissions": ["dms.read", "dms.write"],
 "outcome": "error", "error_type": "ToolError", "duration_ms": 7.7}
```

- **Argument names, never values**: no PII or secrets in logs, but you can still tell what was attempted.
- **`caller_id`** is the Entra object ID (`oid`), so you can trace a call to a person or an agent identity.
- **`outcome`**: `ok`, `input_required` (waiting for confirmation), `tool_error` (an `isError` result), `denied` (authorization) or `error` (an exception, including policy refusals; `error_type` says which).

Container Apps ships stdout/stderr to Log Analytics ([log monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)).
This query runs against the real workspace:

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-mcp-mcpshow" and Log_s has "\"event\": \"tool_call\""
| extend e = parse_json(substring(Log_s, indexof(Log_s, "{")))
| project TimeGenerated, tool = tostring(e.tool), outcome = tostring(e.outcome),
          caller = tostring(e.caller_kind), ms = todouble(e.duration_ms), cid = tostring(e.correlation_id)
| order by TimeGenerated desc
```

Live tail from a terminal:

```bash
az containerapp logs show -g rg-mcpshow -n ca-mcp-mcpshow --follow --format text | grep tool_call
```

Set `APPLICATIONINSIGHTS_CONNECTION_STRING` to add OpenTelemetry traces through
[azure-monitor-opentelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable).

---

## 9. Enterprise questions, answered

**How do you stop prompt injection from making the agent do something bad?**
You can't stop the model from reading malicious text, so don't rely on it. Limits are enforced
in code (15% cap, $500 limit), permissions come from the token, not the prompt, and costly
actions need a human confirmation. The demo lead contains an injected "apply a discount"
instruction; the policy refuses anyway. See [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

**Does the agent act as the user or as itself?**
Both are supported, and the token says which. People sign in (delegated scopes, `caller_kind: user`).
Agents use their own managed identity with app roles (`caller_kind: app`). Agents can never be managers.

**Why not pass the user's token to the backend? Uber's MCP Gateway relays it.**
The [spec forbids token passthrough](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization):
the token's audience is the MCP server, and passing it on creates confused-deputy risk. The server
calls the backend with its own credential and forwards only the caller's ID.
[Uber's gateway](https://www.uber.com/us/en/blog/designing-mcp-gateway/) relays an internal user token through its own service mesh and
access-control system, inside one company's trust domain. If a backend must act as the user, the
Entra answer is the [on-behalf-of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow):
the server exchanges the caller's token for a new one whose audience is the backend. The backend
then sees the user, and no token is ever accepted outside its own audience.

**Why mask personal data in the server instead of at the gateway?**
Masking lives next to the data model, so it changes with the schema and is covered by tests
(`test_masking`, `test_create_lead_returns_masked_data`). Rewriting MCP responses in API Management
is a trap: Microsoft's guidance says [not to read `context.Response.Body` in MCP server policies](https://learn.microsoft.com/en-us/azure/api-management/expose-existing-mcp-server),
because it forces response buffering and breaks streaming. A gateway that owns many servers (like
Uber's) can still add a second redaction layer, built for streaming.

**How do I revoke an agent's access?**
Remove its app role assignment in Entra (or disable its service principal). New tokens won't carry
the role, and existing tokens expire (about an hour).

**How do you audit who did what?**
One structured line per call with the caller's object ID, tool, outcome and a correlation ID, in
Log Analytics. See [section 8](#8-observability-and-traceability).

**What happens when the backend is slow or down?**
Per-attempt deadlines, retries for reads only, a circuit breaker, and `isError` results the model
can explain to the user. Try `./scripts/demo.sh chaos errors`.

**Can it scale?**
The server is stateless (2026-07-28), so Container Apps scales replicas horizontally. Before going
past one replica with the reference build, set `REQUEST_STATE_KEYS` so confirmations work on any replica. The rate limit already lives in API Management.

**Where is the data, and what leaves the backend?**
Canada Central. Tools return the minimum, and personal data is masked before the model sees it.

**Why API Management in front?**
One public entry with one rate limit per caller across all replicas, plus a place for IP filtering
and a catalog when you run many servers. [APIM's MCP support](https://learn.microsoft.com/en-us/azure/api-management/mcp-server-overview)
covers tools (not resources or prompts). The server still validates every token itself (defence in depth).
The demo uses the Developer tier (static IP, no SLA); use Premium or Premium v2 in production.

**Is the network private?**
The apps run in a virtual network. Key Vault has public access off and ACR is pulled over private
endpoints. ACR's public endpoint stays on but denies everyone except the region's ACR build service,
so remote builds keep working, and a CI runner only while it pushes (`scripts/acr-access.sh`).

**How do clients register?**
Known clients are pre-authorized on the Entra app (VS Code, Azure CLI). The spec's order is
pre-registered, then CIMD, then Dynamic Client Registration (deprecated).
See [client registration](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration).

**How do you ship changes safely?**
PR checks (tests, image scan, Bicep lint, what-if), build once, promote the same digest, smoke
tests per environment. See [section 14](../README.md#ship-it).

**Do tool annotations protect us?**
No. They're hints for the host's UI, and clients must treat them as untrusted. Server-side checks do the protecting.

---

## 10. AI engineering lessons

- **The model is a user, not a component.** Treat every tool call like an untrusted request from the internet.
- **Put rules where the model can't reach them.** Policy, math and permissions belong in code.
- **Design tools for the model.** Clear names, narrow jobs, schemas and descriptions that say what not to do. A good tool description is a prompt.
- **Errors are UX.** An `isError` result with a clear sentence lets the model recover and explain; a stack trace doesn't.
- **Identity is the hard part.** Getting `aud`, `iss`, scopes vs roles and pre-authorization right took more effort than any tool.
- **Test the protocol, not just the functions.** Real HTTP, real JWTs, both protocol eras, and a rehearsal script that runs the demo.
- **Production is mostly boring things done consistently:** timeouts, retries, idempotency, audit, scanning, pinning, and promoting the exact artifact you tested.
