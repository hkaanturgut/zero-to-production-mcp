# Dealer Sales Assistant: a production-grade MCP server

Workshop companion for **"From Zero to Production MCP Server: Turn Any API Into an Agent Tool"**
(MCP Dev Summit Toronto, 5 Oct 2026).

A remote MCP server that lets a salesperson's agent search inventory, quote all-in prices,
estimate payments and book test drives at a **fictional** Toronto used-car dealer. The
scenario is only the showcase. The point is the patterns: authentication, least privilege,
human confirmation, secrets the model never sees, failure handling, observability, and a
Terraform + GitHub Actions path to Azure.

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
| `agent` | app-only, roles `dms.read dms.write` (like a Foundry agent) | 9 tools, never manager |
| `manager` | user, adds `dms.manager` | 11 tools, big discounts with confirmation |

Local tokens are signed by a key in `.dev/` (git-ignored) and only work with `AUTH_MODE=local`.
In Azure the server runs with `AUTH_MODE=entra` and trusts only Microsoft Entra ID.

## Run the tests

```bash
uv run pytest -q          # 65 tests: auth, policy, confirmation, resilience, secret hygiene
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

## Deploy to Azure

1. **Bootstrap once** (platform admin, local state):
   `terraform -chdir=infra/bootstrap apply -var subscription_id=... -var github_repository=owner/repo`
2. **Copy the `github_variables` output** into GitHub:
   repository variables `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `ACR_LOGIN_SERVER`,
   `ACR_ID`, `TFSTATE_RG`, `TFSTATE_ACCOUNT`, `BUILD_CLIENT_ID`, `PLAN_CLIENT_ID_dev`,
   `PLAN_CLIENT_ID_prod`; environment variable `APPLY_CLIENT_ID` on the `dev` and `prod`
   environments. None of these are secrets.
3. **Protect `prod`**: add required reviewers on the GitHub Environment.
4. **Open a PR**: CI runs tests, image scan, Terraform static checks and posts a plan per environment.
5. **Merge**: `deploy.yml` builds one image, deploys dev, smoke-tests it, then waits for prod approval.
6. **Connect a Foundry agent**: see `docs/foundry-agent.md`.

Rollback: run `deploy` manually with a previous `image_tag`.

## Layout

```
src/dms/        mock dealer system (FastAPI, API key, chaos switch)
src/server/     MCP server (FastMCP 4, spec 2026-07-28)
tests/          pytest suite over real HTTP with real JWTs
infra/          bootstrap, platform module, dev/prod stacks
.github/        ci.yml (PR), deploy.yml (main), _deploy-env.yml (reusable)
docs/           HLD pointer, Foundry agent setup, production checklist
```
