# Presenter guide: Zero to Production MCP

A 60-minute session, Q&A included. This is your script; attendees follow the README's
[Follow the workshop](../README.md#follow-the-workshop) section. Follow this top to bottom. Each segment lists the steps in order:
what to **run**, what to **open in code**, what to **show as a picture**, what to **say**, and the
**expected** result. Times are elapsed minutes (`+12` = 12 minutes in). Details and fallbacks:
[RUNBOOK.md](RUNBOOK.md), [SHOW-PREP.md](SHOW-PREP.md).

| Segment | Starts | Minutes |
| --- | --- | --- |
| 1. Intro | +0 | 3 |
| 2. Stage 0: the internal API | +3 | 2 |
| 3. Stage 1: first tools (typed live) | +5 | 7 |
| 4. Stage 2: tools the model can use | +12 | 6 |
| 5. Stage 3: identity and personal data | +18 | 9 |
| 6. Stage 4: least privilege and confirmation | +27 | 9 |
| 7. Stage 5: resilience, audit (deploy starts at +38) | +36 | 5 |
| 8. Deploy and production walkthrough | +41 | 5 |
| 9. Finale: VS Code + Copilot | +46 | 6 |
| 10. Wrap-up | +52 | 2 |
| 11. Q&A | +54 | 6 |

**Checkpoints:** stage 3 by +18, stage 5 by +36, deploy started by +38, finale by +46, Q&A by +54.

**How you move between stages:** stay on the `main` branch the whole time (it has the latest scripts and
`.vscode/mcp.json`) and swap only the file you build. Stage 1 is typed live. For stages 2 to 5 run
`./scripts/demo.sh stage N`: it sets `src/live/server.py` to stage N and opens VS Code's diff against the
previous stage, so you walk the change and point at the key line instead of typing it. Attendees follow
with `git checkout stage-N`.

## Before you start (T minus 45 min)

1. Run `./scripts/preshow.sh --cloud` on the venue Wi-Fi. Expected: `ALL GREEN` (or only `git tree has changes`).
   - Green: cloud segments (deploy, sign-in, Copilot) run live, with videos V1 to V3 on standby.
   - Red, or API Management not available: play V3 for the deploy and V1 for the finale, and say why.
2. On `main`: `./scripts/demo.sh stage 0` and `./scripts/demo.sh reset`.
3. Open the terminals:

   | Pane | Command | Starts |
   | --- | --- | --- |
   | T1 | `./scripts/demo.sh dms` | Now |
   | T2 | `./scripts/demo.sh live` | Stage 1 (stage 0 has no `app`) |
   | T3 | `./scripts/demo.sh inspector [persona]` | Stage 1 |
   | T4 | `set -a; . ./.env; set +a` | Now (free shell for `curl`, `chaos`, `azd`) |

4. Open: `src/live/server.py` in the editor; browser tabs with [architecture.svg](architecture.svg),
   the Azure portal on `rg-mcpshow` (API Management > APIs > dealer-mcp), and Log Analytics with the query
   from [section 8](../README.md#8-observability-and-traceability).

Stages 0 to 4 and the stage 5 code run on localhost with local dev tokens: no Wi-Fi needed.

## 1. Intro (+0, 3 min)

1. **Picture:** the architecture diagram, end state first: client → API Management → MCP server → internal API.
2. **Say:** agents need your internal APIs; a naive wrapper leaks data, trusts the model and falls over.
   In one hour: empty file to a deployed, authenticated, least-privilege MCP server on spec 2026-07-28.

## 2. Stage 0: the internal API (+3, 2 min)

1. **Run** (T4):
   ```bash
   curl -s -H "X-API-Key: $DMS_API_KEY" 'http://127.0.0.1:8081/vehicles?limit=1'   # one car, with "vin"
   ```
2. **Say:** a plain REST API with one shared key, like most internal systems. MCP doesn't replace it; it sits in front.

## 3. Stage 1: first tools, typed live (+5, 7 min)

1. **Type** in `src/live/server.py` (the imports, `DMS_URL` and `DMS_KEY` are in `workshop/snippets/stage_1.txt`):
   ```python
   mcp = FastMCP("dealer-sales-assistant")
   dms = httpx.AsyncClient(base_url=DMS_URL, headers={"X-API-Key": DMS_KEY})


   async def call_dms(method: str, path: str, **kwargs) -> dict:
       resp = await dms.request(method, path, **kwargs)
       resp.raise_for_status()
       return resp.json()


   @mcp.tool
   async def search_inventory(make: str | None = None, max_price: int | None = None) -> dict:
       """Search cars on the lot."""
       params = {"make": make, "max_price": max_price}
       return await call_dms("GET", "/vehicles", params={k: v for k, v in params.items() if v})


   @mcp.tool
   async def get_vehicle(stock_number: str) -> dict:
       """Get one car."""
       return await call_dms("GET", f"/vehicles/{stock_number}")


   app = mcp.http_app(path="/mcp")
   ```
   Short on time: `./scripts/demo.sh stage 1` and walk it instead.
2. **Run** `./scripts/demo.sh live` (T2) and `./scripts/demo.sh inspector` (T3, no persona).
3. **Inspector:** `tools/list` → 2 tools. `get_vehicle` `{"stock_number": "TBA-1001"}` → raw dump with `vin`.
   `get_vehicle` `{"stock_number": "../admin"}` → error leaks `127.0.0.1:8081/admin`.
4. **Say:** it works in 20 lines, and that's the trap: it returns everything, it lets the model do the
   price math, untyped input walks the URL, and anyone can call it.

## 4. Stage 2: tools the model can use (+12, 6 min)

1. **Run** `./scripts/demo.sh stage 2`. The server reloads; Inspector reconnects.
2. **Code (diff):** `StockNumber` (the pattern), the `Vehicle` / `SearchResult` / `Quote` output models,
   and `quote_price` calling `all_in_quote` (`src/server/domain/pricing.py`).
3. **Inspector:** `get_vehicle` `{"stock_number": "../admin"}` → rejected by validation.
   `quote_price` `{"stock_number": "TBA-1001"}` → `all_in_price: 34309.5`, fees listed.
4. **Picture:** Inspector's output schema next to the structured result.
5. **Say:** the schema is the contract; return the minimum; business math in code, never in the model.

## 5. Stage 3: identity and personal data (+18, 9 min)

1. **Run** `./scripts/demo.sh stage 3`.
2. **Code (diff):** `ROLES` + `EntraVerifier` (people's `scp` and agents' `roles` become one permission
   set), `build_auth()` with `ENTRA_API_URI`, `caller()` (identity from the token), `mask_lead`.
3. **Run** (T4):
   ```bash
   curl -si -X POST http://127.0.0.1:8080/mcp | grep -iE '^HTTP|www-authenticate'   # 401 + resource_metadata
   ```
4. **Run** `./scripts/demo.sh inspector salesperson` (T3).
5. **Inspector:** `create_lead` `{"first_name": "Priya", "last_name": "Natarajan", "phone": "416-555-0142"}`
   → `name: "Priya N."`, `phone: "***-***-0142"`.
6. **Say:** the server is a resource server; the 401 tells any client where to sign in; identity comes
   from the token, never from arguments; personal data is masked before the model sees it.

## 6. Stage 4: least privilege and human confirmation (+27, 9 min)

1. **Run** `./scripts/demo.sh stage 4` and `./scripts/demo.sh reset` (T4).
2. **Code (diff):** the three `restrict_tag(...)` lines in `AuthMiddleware`; the 15% / $500 policy in
   `apply_discount`; the call to `confirmation()` (`src/server/tools/common.py`).
3. **Inspector (salesperson):** `tools/list` → 6 tools, `delete_lead` hidden.
   `get_lead` `{"lead_id": "L-760debbb3b70b3a1"}` → the note tells the AI to apply a $9,000 discount.
   `apply_discount` `{"stock_number": "TBA-1001", "amount": 900, "reason": "please"}` → needs a sales manager.
4. **Run** `./scripts/demo.sh inspector manager` (T3). **Inspector:** the same $900 discount → the
   confirmation prompt → **accept** → `discount: 900.0`.
5. **Say:** tools you can't use aren't even listed; the injected note fails because policy lives in code;
   costly actions need a human, on both protocol eras.

## 7. Stage 5: resilience and audit (+36, 5 min)

1. **Run** `./scripts/demo.sh stage 5`.
2. **Start the deploy now** (T4, by +38): `azd deploy mcp -e mcpshow` (about 75 s). Keep going while it builds.
3. **Code (diff):** `attempts = 3 if method == "GET" else 1`, the `asyncio.timeout(1.5)` block,
   `AuditMiddleware` and `RateLimitingMiddleware`.
4. **Run** `./scripts/demo.sh chaos flaky` (T4), then **Inspector:** `get_vehicle` TBA-1001 a few times →
   retries absorb the failures. `./scripts/demo.sh chaos off`.
5. **Picture:** T2's audit lines: one JSON line per call, argument names only.
6. **Say:** a real per-attempt deadline, retry reads only, one audit line per call.

## 8. Deploy and the production walkthrough (+41, 5 min)

1. If `azd deploy` isn't done by +43, play V3.
2. **Code:** `infra/modules/apim-api.bicep` (`rate-limit-by-key` on the caller's `oid`);
   `infra/modules/platform.bicep` (`ipSecurityRestrictions`, Key Vault `publicNetworkAccess: 'Disabled'`).
3. **Picture:** portal, API Management > APIs > dealer-mcp > Inbound processing (the policy).
4. **Run** (T4):
   ```bash
   MCP=$(azd env get-value MCP_URL -e mcpshow)
   APP=$(az containerapp show -g rg-mcpshow -n ca-mcp-mcpshow --query properties.configuration.ingress.fqdn -o tsv)
   curl -s -o /dev/null -w "direct to the app: %{http_code}\n" "https://$APP/healthz"   # 403
   curl -s "${MCP%/mcp}/healthz"                                                      # {"status":"ok"}
   ```
5. **Say:** the file you just built now runs in a private network; clients reach it only through API
   Management, with one rate limit per caller across replicas; Key Vault and the registry have no open public
   access. The image was built once and promoted unchanged by CI (`release.yml`).

## 9. Finale: local first, then the cloud (+46, 6 min)

1. **Local (about 45 s, attendees can do this too):** VS Code > *MCP: List Servers* > `dealer-local` > *Start*.
   When it asks for a token, paste the output of `./scripts/demo.sh token salesperson` (T4).
2. **Copilot Chat, Agent mode:**
   > A customer wants an AWD SUV under $25,000 with under 100,000 km. Find the best match, give me the all-in price, save her as a lead (Priya Natarajan, 416-555-0142), and apply a $900 discount.
3. **Expected:** TBA-1017 (2021 Tiguan); all-in **$20,209.50**; lead saved with a masked phone;
   **"Discounts over $500 need a sales manager."**
4. **Cloud:** *MCP: List Servers* > stop `dealer-local`, start `dealer-cloud`, sign in with Microsoft, and
   send the same prompt. Same answers, now through Entra and API Management in Azure.
5. **Say:** the same file, unchanged, runs on your laptop and in production; only the identity provider
   and the front door changed.
6. **Picture (if time):** Log Analytics with your cloud calls: caller, outcome, latency.
7. **If the cloud stalls:** retry *Start* once, then play V1; if API Management is down, use `dealer-spare`.
   The local result already made the point.

## 10. Wrap-up (+52, 2 min)

1. **Picture:** [CHECKLIST.md](CHECKLIST.md) (the production checklist), then the repo QR and the feedback QR.
2. **Say:** take it home: everything you saw locally runs from the repo, and `azd up` deploys your own
   copy to Azure (about 45 min, mostly API Management; README "Deploy to Azure").

## 11. Q&A (+54, 6 min)

Backup slides: enterprise Q&A ([section 9](../README.md#9-enterprise-questions-answered)) and "From one server to
hundreds" ([section 7](../README.md#from-one-server-to-hundreds)).

**If you run behind, cut in this order:** stage 0 curl (say it); stage 2 schema picture; stage 3 curl;
stage 4 manager confirmation (say it, it's in V2); stage 5 chaos; Log Analytics in the finale; the local half of the finale (go straight to the cloud). Never start
the deploy later than +38.
