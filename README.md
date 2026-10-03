[![release](https://github.com/hkaanturgut/zero-to-production-mcp/actions/workflows/release.yml/badge.svg)](https://github.com/hkaanturgut/zero-to-production-mcp/actions/workflows/release.yml)

# Dealer Sales Assistant: a production-grade MCP server

Workshop companion for **"From Zero to Production MCP Server: Turn Any API Into an Agent Tool"**
(MCP Dev Summit Toronto, 5 Oct 2026).

A remote MCP server that lets a salesperson's agent search inventory, quote all-in prices,
estimate payments and book test drives at a **fictional** Toronto used-car dealer. The
scenario is only the showcase. The point is the patterns: authentication, least privilege,
human confirmation, secrets the model never sees, failure handling, observability, and a
Bicep + azd path to Azure, with GitHub Actions for CI/CD.

All cars, customers and leads are synthetic.

## Quick start (offline, about 2 minutes)

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

| Persona | Token | Sees |
| --- | --- | --- |
| `readonly` | user, `dms.read` | 5 read tools |
| `salesperson` | user, `dms.read dms.write` | 9 tools, discounts up to $500 |
| `agent` | app-only, roles `dms.agent.read dms.agent.write` (like a Foundry agent) | 9 tools, never manager |
| `manager` | user, adds `dms.manager` | 11 tools, big discounts with confirmation |

Local tokens are signed by a key in `.dev/` (git-ignored) and only work with `AUTH_MODE=local`.
In Azure the server runs with `AUTH_MODE=entra` and trusts only Microsoft Entra ID.

## Run the tests

```bash
uv run pytest -q          # 73 tests: auth, policy, confirmation, resilience, secrets, every live stage
uv run ruff check src tests
```

## What to look at

| Practice | Where |
| --- | --- |
| Token validation, `scp` + `roles` merged into one permission set | `src/server/auth.py` |
| Permission per tool tag, hidden tools, step-up signal | `src/server/app.py` (AuthMiddleware) |
| Human confirmation with the 2026-07-28 multi round-trip flow | `src/server/tools/common.py` (`confirmation`) |
| Business rules in code, not prompts (discount limits, injection-proof) | `src/server/domain/policy.py` |
| All-in pricing with Decimal math | `src/server/domain/pricing.py` |
| PII masking, untrusted text marked as data | `src/server/domain/masking.py` |
| Timeouts, read-only retries, circuit breaker, idempotency keys | `src/server/backend/mock_client.py`, `tools/common.py` |
| Audit event per call, no argument values logged | `src/server/middleware.py` |
| Swappable backend (`DmsBackend` Protocol) | `src/server/backend/base.py` |
| Tool contract guardrails in CI | `tests/test_tool_contracts.py` |
| Failure injection for live demos | `POST /_chaos {"mode": "slow" \| "errors" \| "flaky" \| "off"}` on the DMS |

## Deploy to Azure (Bicep + azd)

Requires [azd](https://aka.ms/azd) and the Azure CLI. Your account needs rights to create
resource groups and app registrations.

```bash
azd auth login && az login
azd env new mcpdev --location canadacentral
azd up                       # provision (about 6 to 8 min) + build in ACR + deploy
azd env get-value MCP_URL    # https://ca-mcp-mcpdev.<region>.azurecontainerapps.io/mcp
```

| Command | When |
| --- | --- |
| `azd provision` | Infra only (run before the talk) |
| `azd deploy mcp` | Ship new server code only, about 2 to 3 min (on stage) |
| `azd env set MCP_COMMAND server && azd provision` | Switch the cloud app to the full reference build |
| `azd env set ASSIGN_MANAGER_ROLE true && azd provision` | Make yourself a sales manager (confirmation demo in VS Code) |
| `azd env set DEPLOY_FOUNDRY true && azd provision` | Add a Foundry account, project and model |
| `azd down --purge --force` | Delete everything, including the soft-deleted Key Vault |

What gets created: resource group, Log Analytics + App Insights, managed identity, ACR
(admin disabled, base image mirrored in), Key Vault (RBAC, generated service key),
Container Apps environment with `ca-mcp-<env>` (public) and `ca-dms-<env>` (internal only),
and an Entra app registration with 2 delegated scopes, 3 app roles and VS Code pre-authorized.

**Connect VS Code:** put the `MCP_URL` in `.vscode/mcp.json` as an `http` server, then
*MCP: List Servers > Start*. VS Code signs you in with Microsoft automatically.

## CI/CD

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

## Layout

```
src/dms/        mock dealer system (FastAPI, API key, chaos switch)
src/server/     MCP server (FastMCP 4, spec 2026-07-28)
tests/          pytest suite over real HTTP with real JWTs
infra/          main.bicep + modules (platform, entra, foundry), azd parameters
workshop/       stage files 0-5 and paste snippets for the live build
src/live/       the file you build on stage (equals workshop/stages/stage_5.py on main)
.github/        ci.yml (PR checks + what-if), release.yml (main: dev, then prod)
docs/           HLD pointer, Foundry agent setup, production checklist
```
