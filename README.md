[![release](https://github.com/hkaanturgut/zero-to-production-mcp/actions/workflows/release.yml/badge.svg)](https://github.com/hkaanturgut/zero-to-production-mcp/actions/workflows/release.yml)

# Zero to Production MCP: turn any API into an agent tool

Workshop companion for **"From Zero to Production MCP Server: Turn Any API Into an Agent Tool"**
(MCP Dev Summit Toronto, 5 Oct 2026).

A remote MCP server that lets a salesperson's agent search inventory, quote all-in prices,
estimate payments and book test drives at a **fictional** Toronto used-car dealer. The
scenario is only the showcase. The point is the patterns: authentication, least privilege,
human confirmation, secrets the model never sees, failure handling, observability, and a
Bicep + azd path to Azure, with GitHub Actions for CI/CD.

All cars, customers and leads are synthetic.

**Contents**

- **[Demo: presenter guide](#demo-presenter-guide)** (start here on stage)

1. [MCP in five minutes](#1-mcp-in-five-minutes) · [Why MCP instead of a plain REST API?](#why-mcp-instead-of-a-plain-rest-api)
2. [Architecture](#2-architecture)
3. [The tools](#3-the-tools)
4. [Security](#4-security)
5. [Development](#5-development)
6. [Operations and maintenance](#6-operations-and-maintenance)
7. [Scalability and reliability](#7-scalability-and-reliability)
8. [Observability and traceability](#8-observability-and-traceability)
9. [Enterprise questions, answered](#9-enterprise-questions-answered)
10. [AI engineering lessons](#10-ai-engineering-lessons)
11. [Quick start](#11-quick-start-offline-about-2-minutes) · [Tests](#12-run-the-tests) · [Deploy](#13-deploy-to-azure-bicep--azd) · [CI/CD](#14-cicd) · [Connect a client](#15-connect-a-client) · [Layout](#16-layout)

---

## Demo: presenter guide

Follow this top to bottom on stage. Each segment lists the steps in order: what to **run**, what to
**open in code**, what to **show as a picture**, what to **say**, and the **expected** result.
Exact paste blocks and fallbacks per stage: [docs/RUNBOOK.md](docs/RUNBOOK.md). Videos and backups:
[docs/SHOW-PREP.md](docs/SHOW-PREP.md).

> Read this guide from the `main` branch on GitHub. During the workshop your working tree moves
> through the `stage-N` branches, whose copy of this README is older.

### Before you start (T minus 45 min)

1. Run `./scripts/preshow.sh --cloud` on the venue Wi-Fi. Expected: `ALL GREEN` (or only `git tree has changes`).
   - Green: cloud segments (deploy, sign-in, Copilot) run live, with videos V1 to V3 on standby.
   - Red, or API Management not available: play V3 for the deploy and V1 for the finale, and say why.
2. Run `git checkout stage-0` and `./scripts/demo.sh reset`.
3. Open the terminals:

   | Pane | Command | Starts |
   | --- | --- | --- |
   | T1 | `./scripts/demo.sh dms` | Now |
   | T2 | `./scripts/demo.sh live` | Stage 1 (stage 0 has no `app`) |
   | T3 | `./scripts/demo.sh inspector [persona]` | Stage 1 |
   | T4 | `set -a; . ./.env; set +a` | Now (free shell for `curl`, `chaos`, `azd`) |

4. Open: editor with `src/live/server.py` (left) and `workshop/snippets/stage_N.txt` (right); browser tabs
   with [docs/architecture.svg](docs/architecture.svg), the Azure portal on `rg-mcpshow`, the repo's
   Actions page, and Log Analytics (query from [section 8](#8-observability-and-traceability)).

Stages 0 to 4 and the stage 5 code run on localhost with local dev tokens: no Wi-Fi needed.

### 1. Intro (10:50, 5 min)

1. **Picture:** the architecture diagram. Walk the 7 numbered steps: this is where we end up.
2. **Say:** every company has internal APIs and agents need them; a naive wrapper leaks data, trusts the
   model and falls over. In 85 minutes: empty file to a deployed, authenticated, least-privilege MCP server.
3. **Say:** spec 2026-07-28 is stateless (no `initialize`), uses multi round-trip for human input, and
   prefers CIMD over dynamic client registration. Attendees can follow with `git checkout stage-<N-1>`.

### 2. Stage 0: the internal API (10:55, 5 min)

1. **Run** (T4):
   ```bash
   curl -i 'http://127.0.0.1:8081/vehicles?limit=1'                              # 401
   curl -s -H "X-API-Key: $DMS_API_KEY" 'http://127.0.0.1:8081/vehicles?limit=1'  # one car, with "vin"
   ```
2. **Code:** `src/dms/app.py`, the endpoint list (`/vehicles`, `/dealer/fees`, `/leads`), all behind one `X-API-Key`.
3. **Picture:** the "Why MCP instead of a plain REST API?" table ([section 1](#why-mcp-instead-of-a-plain-rest-api)).
4. **Say:** the MCP server sits in front of this API; the agent never sees the API, its key or its network.

### 3. Stage 1: first tools (11:00, 10 min)

1. **Paste** `workshop/snippets/stage_1.txt` after the docstring. **Type** `mcp`, `dms`, `call_dms`,
   `search_inventory`, `get_vehicle` and `app = mcp.http_app(path="/mcp")` (text in the runbook).
2. **Run** `./scripts/demo.sh live` (T2) and `./scripts/demo.sh inspector` (T3, no persona).
3. **Inspector:** `tools/list` → 2 tools. `get_vehicle` `{"stock_number": "TBA-1001"}` → raw dump with `vin`.
   `get_vehicle` `{"stock_number": "../admin"}` → error leaks `127.0.0.1:8081/admin`.
4. **Code:** point at `call_dms()` and the untyped `stock_number: str`.
5. **Say:** it works in 20 lines, and that's the trap. Problem 1: it returns everything (VIN). Problem 2:
   `list_price` has no fees, so the model will do the math. Problem 3: untyped input walks the URL and
   leaks a hostname. And anyone can call it.

### 4. Stage 2: tools the model can use (11:10, 12 min)

1. **Paste** `workshop/snippets/stage_2.txt` (delete the old `@mcp.tool` functions where a block says
   REPLACE). **Type** `StockNumber` and `quote_price`.
2. **Inspector:**
   - `tools/list` → the `body_type` enum in the input schema, an output schema on every tool.
   - `get_vehicle` `{"stock_number": "../admin"}` → rejected by validation, never reaches the DMS.
   - `get_vehicle` `{"stock_number": "TBA-1001"}` → `Vehicle`, no `vin`.
   - `quote_price` `{"stock_number": "TBA-1001"}` → `all_in_price: 34309.5`, the fees listed.
3. **Run** `curl -s http://127.0.0.1:8080/healthz` → `{"status":"ok"}`.
4. **Code:** `StockNumber`, the `Vehicle` / `SearchResult` / `Quote` models, `quote_price` calling
   `all_in_quote` (`src/server/domain/pricing.py`, Decimal math).
5. **Picture:** Inspector's output schema next to the structured result.
6. **Say:** the schema is the contract; output models return the minimum; business math in code.

### 5. Stage 3: identity and personal data (11:22, 15 min)

1. **Paste** `workshop/snippets/stage_3.txt`. **Type** `ROLES`, `EntraVerifier` and `caller()`.
   While pasting `build_auth()`, point at `ENTRA_API_URI` (scopes on the identifier URI).
2. **Run** (T4):
   ```bash
   curl -si -X POST http://127.0.0.1:8080/mcp | grep -iE '^HTTP|www-authenticate'   # 401 + resource_metadata
   curl -s http://127.0.0.1:8080/.well-known/oauth-protected-resource/mcp            # authorization server, scopes
   ```
3. **Run** `./scripts/demo.sh inspector salesperson` (T3, restart with a token).
4. **Inspector:** `create_lead` `{"first_name": "Priya", "last_name": "Natarajan", "phone": "416-555-0142"}`
   → `name: "Priya N."`, `phone: "***-***-0142"`. `get_vehicle` `{"stock_number": "TBA-9999"}` → error
   without internal hostnames.
5. **Code:** `ROLES` + `EntraVerifier` (people's `scp` and agents' `roles` become one permission set);
   `caller()` (identity from the token, never from arguments); `mask_lead` in `src/server/domain/masking.py`.
6. **Picture:** a decoded token (shows `scp`, `oid`, `idtyp`):
   ```bash
   ./scripts/demo.sh token salesperson | python3 -c "import sys,json,base64; p=sys.stdin.read().split('.')[1]; print(json.dumps(json.loads(base64.urlsafe_b64decode(p + '==')), indent=1))"
   ```
7. **Say:** the server is a resource server; the 401 tells any client where to sign in; personal data is
   masked before the model sees it.

### 6. Stage 4: least privilege and human confirmation (11:37, 15 min)

1. **Paste** `workshop/snippets/stage_4.txt`. **Type** the three `restrict_tag(...)` lines and the
   15% / $500 policy in `apply_discount`.
2. **Run** `./scripts/demo.sh reset` (T4) and `./scripts/demo.sh inspector salesperson` (T3).
3. **Inspector (salesperson):**
   - `tools/list` → 6 tools, `delete_lead` hidden.
   - `get_lead` `{"lead_id": "L-760debbb3b70b3a1"}` → the note asks the AI to apply a $9,000 discount.
   - `apply_discount` `{"stock_number": "TBA-1001", "amount": 9000, "reason": "pre-approved"}` → 15% maximum.
   - `apply_discount` `{"stock_number": "TBA-1001", "amount": 900, "reason": "please"}` → needs a sales manager.
4. **Run** `./scripts/demo.sh inspector manager` (T3).
5. **Inspector (manager):** `tools/list` → 7 tools. `apply_discount` 900 → **decline** → "Nothing was
   changed"; again → **accept** → `discount: 900.0`.
6. **Code:** `apply_discount` (policy in code); `confirmation()` in `src/server/tools/common.py` (2026-07-28
   multi round-trip, classic elicitation for older clients).
7. **Picture:** the persona table ([section 3](#3-the-tools)): who sees which tools.
8. **Say:** the injected note fails twice: it's data, and the cap stops it anyway. Managers get a role,
   never a consentable scope; agents never get manager rights.

### 7. Stage 5: resilience, audit, rate limit (11:52, 6 min)

1. **Run** `./scripts/demo.sh chaos flaky` (T4). **Inspector** (salesperson): `get_vehicle` TBA-1001 5 to 8
   times → some generic failures. That's the problem.
2. **Paste** `workshop/snippets/stage_5.txt`. **Type** the `attempts = 3 if method == "GET" else 1` line and
   the `async with asyncio.timeout(1.5):` block in `call_dms`.
3. **Start the deploy now** (go to segment 8, step 1), then come back here while it builds.
4. **Inspector:** `get_vehicle` TBA-1001 again → retries absorb the failures. `chaos slow` → `search_inventory`
   `{}` fails fast with "(retryable)". `chaos errors` → `create_lead` fails once, never retried. `chaos off`.
5. **Picture:** T2's audit lines: one JSON line per call, argument names only (the phone number is absent).
6. **Code:** `call_dms()` retry loop; `AuditMiddleware` in `src/server/middleware.py`; `RateLimitingMiddleware`.
7. **Say:** httpx timeouts are per phase, so the real deadline is `asyncio.timeout`; retry reads only;
   every call leaves one audit line.

### 8. Deploy and the production walkthrough (11:58, 5 min)

1. **Run** (T4, by 11:58 at the latest): `azd deploy mcp -e mcpshow` (about 75 s). If it isn't done by 12:01, play V3.
2. **While it builds, code:**
   - `infra/main.bicep`: the modules (network, API Management, platform, Entra).
   - `infra/modules/apim-api.bicep`: `rate-limit-by-key` keyed on the caller's `oid`.
   - `infra/modules/platform.bicep`: `ipSecurityRestrictions` on `ca-mcp`, Key Vault `publicNetworkAccess: 'Disabled'`, the ACR firewall.
3. **While it builds, portal** (`rg-mcpshow`): API Management > APIs > dealer-mcp > Inbound processing
   (the policy); `ca-mcp-mcpshow` > Ingress (IP restrictions); `vnet-mcpshow` and the two private endpoints;
   the Key Vault > Networking (public access disabled).
4. **When it's done, run** (T4):
   ```bash
   MCP=$(azd env get-value MCP_URL -e mcpshow)
   APP=$(az containerapp show -g rg-mcpshow -n ca-mcp-mcpshow --query properties.configuration.ingress.fqdn -o tsv)
   curl -s -o /dev/null -w "direct to the app: %{http_code}\n" "https://$APP/healthz"   # 403
   curl -s "${MCP%/mcp}/healthz"                                                      # {"status":"ok"}
   curl -s "${MCP%/mcp}/.well-known/oauth-protected-resource/mcp"                     # names the gateway URL
   ```
5. **Say:** the file you just typed now runs in a private network; clients reach it only through API
   Management, which applies one rate limit per caller across all replicas; Key Vault and the registry
   have no open public access. (azd prints the app's own URL as "Endpoint"; that one answers 403 by design.)

### 9. How it ships (12:03, 2 min)

1. **Picture:** the repo's Actions page, the latest `release` run graph: changes → dev → prod.
2. **Code:** `.github/workflows/release.yml`: build once, scan, `az acr import` of the same digest into prod;
   `scripts/acr-access.sh` opens the registry firewall only while CI pushes.
3. **Say:** what was tested in dev is byte-for-byte what runs in prod; PRs show a what-if before anything changes.

### 10. Finale: VS Code + GitHub Copilot (12:05, 6 min)

1. **VS Code:** *MCP: List Servers* > `dealer-cloud` > *Start*. Sign in with Microsoft.
2. **Copilot Chat, Agent mode:**
   > A customer wants an AWD SUV under $25,000 with under 100,000 km. Find the best match, give me the all-in price, save her as a lead (Priya Natarajan, 416-555-0142), and apply a $900 discount.
3. **Expected:** `search_inventory` → TBA-1017 (2021 Tiguan); `quote_price` → **$20,209.50**; `create_lead`
   with a masked phone; `apply_discount` → **"Discounts over $500 need a sales manager."**
4. **Picture:** Log Analytics with the query from [section 8](#8-observability-and-traceability): your calls,
   with caller, outcome and latency.
5. **Say:** the same file, unchanged, now runs behind Entra and API Management in Azure.
6. **If it stalls:** retry *Start* once, then play V1; if API Management is down, switch to `dealer-spare`.

### 11. Wrap-up and Q&A (12:11, 4 min)

1. **Picture:** `docs/CHECKLIST.md`, then the repo QR and the feedback QR.
2. **Backup slides for questions:** enterprise Q&A ([section 9](#9-enterprise-questions-answered)) and
   "From one server to hundreds" ([section 7](#from-one-server-to-hundreds)).

**If you run behind:** at 11:22 skip the decoded token; at 11:52 skip `chaos errors`; never start the deploy
later than 11:58; shrink segments 8 and 9 to one picture each (the API Management policy and the Actions graph).

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

![Solution architecture: agent clients sign in with Microsoft Entra ID and call the MCP server through API Management; the server runs on Azure Container Apps in a private network, calls an internal dealer API with a key from a private Key Vault and audits every call to Log Analytics](docs/architecture.svg)

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

Design notes: [docs/HLD.md](docs/HLD.md). Stage runbook: [docs/RUNBOOK.md](docs/RUNBOOK.md). Show prep and fallbacks: [docs/SHOW-PREP.md](docs/SHOW-PREP.md).

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
`tests/test_resilience_and_safety.py`. The full checklist is in [docs/CHECKLIST.md](docs/CHECKLIST.md).

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
tests per environment. See [section 14](#14-cicd).

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

---

## 11. Quick start (offline, about 2 minutes)

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync
cp .env.example .env                      # then set DMS_API_KEY to any long random string
set -a; source .env; set +a

uv run dms &                              # mock dealer system on :8081
uv run dev-token salesperson > /dev/null  # creates .dev/ keys on first run
uv run server                             # MCP server on :8080/mcp
```

Get a token for a persona and call the server with MCP Inspector:

```bash
TOKEN=$(uv run dev-token salesperson)     # or: manager, agent, readonly
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8080/mcp \
  --transport http --header "Authorization: Bearer $TOKEN" --method tools/list
```

Local tokens are signed by a key in `.dev/` (git-ignored) and only work with `AUTH_MODE=local`.
In Azure the server runs with `AUTH_MODE=entra` and trusts only Microsoft Entra ID.

## 12. Run the tests

```bash
uv run pytest -q          # 76 tests: auth, policy, confirmation, resilience, secrets, hardening, every live stage
uv run ruff check src tests
./scripts/demo.sh rehearse  # 34 runbook steps
```

| File | Covers |
| --- | --- |
| `test_auth.py` | Token validation, scope and role mapping, hidden tools |
| `test_domain.py` | Pricing, HST, finance, policy, masking |
| `test_policy_and_danger.py` | Discount limits, 15% cap, confirmation, prompt-injection resistance |
| `test_legacy_clients.py` | Confirmation for 2025-11-25 clients |
| `test_read_tools.py` | Search, pagination, input validation, quotes |
| `test_write_tools.py` | Leads, idempotency, masking, ownership |
| `test_resilience_and_safety.py` | Timeouts, retries, circuit breaker, error masking, secret hygiene, rate limit, audit |
| `test_tool_contracts.py` | Every tool has one tag, annotations and a schema |
| `test_live_stages.py` | Every workshop stage file |
| `test_hardening.py` | Foreign `Origin` rejected; confirmation across two replicas with and without a shared key |

## 13. Deploy to Azure (Bicep + azd)

Requires [azd](https://aka.ms/azd) (1.35 or later) and the Azure CLI. Your account needs rights
to create resource groups and app registrations.

```bash
azd auth login && az login
azd env new mcpdev --location canadacentral
azd up                       # provision (about 45 min: API Management) + build in ACR + deploy
azd env get-value MCP_URL    # https://apim-mcpdev-<id>.azure-api.net/mcp
```

| Command | When |
| --- | --- |
| `azd provision` | Infra only (run before the talk) |
| `azd deploy mcp` | Ship new server code only, about 80 s (on stage) |
| `azd env set MCP_COMMAND server && azd provision` | Switch the cloud app to the full reference build |
| `azd env set ASSIGN_MANAGER_ROLE true && azd provision` | Make yourself a sales manager (confirmation demo in VS Code) |
| `azd env set DEPLOY_FOUNDRY true && azd provision` | Add a Foundry account, project and model |
| `azd down --purge --force` | Delete everything, including the soft-deleted Key Vault |

## 14. CI/CD

Two GitHub Actions workflows (details in [docs/HLD.md](docs/HLD.md#cicd)):

- `ci.yml` on pull requests: ruff + pytest, Docker build + Trivy scan, Bicep build + lint,
  and an `azd provision --preview` what-if on dev, posted to the job summary.
- `release.yml` on push to `main` or manual run: provisions only when infra changed, builds
  the image once, scans it, deploys to dev, smoke-tests, then promotes the same tag and
  digest to prod with `az acr import` (no rebuild).

Prod runs on push only if the repo variable `PROD_ON_PUSH` is `true`. Otherwise trigger it:

```bash
gh workflow run release.yml -f scope=all -f prod=true
```

| Setting | Level | Value |
| --- | --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION` | Repo variables | CI app registration (OIDC), target subscription and region |
| `AZURE_ENV_NAME` | Environment variable (`dev`, `prod`) | azd env name: `mcpdev`, `mcpshow` |
| `DMS_API_KEY` | Environment secret (`dev`, `prod`) | Service key, written to Key Vault |

Don't run `azd provision` locally on these two envs: the preprovision hook would rotate
`DMS_API_KEY` away from the GitHub secret.

## 15. Connect a client

The server is a standard remote MCP endpoint: Streamable HTTP plus OAuth 2.0 bearer tokens from Entra.

**VS Code + GitHub Copilot.** `.vscode/mcp.json` already has `dealer-cloud`. Run *MCP: List Servers >
dealer-cloud > Start*, sign in with Microsoft, then use Copilot in Agent mode.
See [VS Code MCP servers](https://code.visualstudio.com/docs/copilot/customization/mcp-servers).

**Claude Code.**

```bash
API=$(azd env get-value ENTRA_API_URI)
TOKEN=$(az account get-access-token --scope "$API/dms.read" "$API/dms.write" --query accessToken -o tsv)
claude mcp add --transport http dealer-cloud "$(azd env get-value MCP_URL)" \
  --header "Authorization: Bearer $TOKEN"
```

**MCP Inspector.**

```bash
npx @modelcontextprotocol/inspector@latest --web --transport http \
  --server-url "$(azd env get-value MCP_URL)" \
  --header "Authorization: Bearer $TOKEN" --protocol-era modern
```

**Microsoft Foundry agent.** App-only, with the agent's own identity. See [docs/foundry-agent.md](docs/foundry-agent.md)
and [Foundry MCP tools](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol).

## 16. Layout

```
src/dms/        mock dealer system (FastAPI, API key, chaos switch)
src/server/     MCP server, reference build (FastMCP 4, spec 2026-07-28)
src/live/       the file you build on stage (equals workshop/stages/stage_5.py on main)
tests/          pytest suite over real HTTP with real JWTs
infra/          main.bicep + modules (platform, entra, foundry), azd parameters
workshop/       stage files 0-5, paste snippets, rehearsal script
.github/        ci.yml (PR checks + what-if), release.yml (main: dev, then prod)
docs/           HLD, stage runbook, architecture diagram, Foundry agent setup, production checklist
```
