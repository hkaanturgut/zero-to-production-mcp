# Show prep: MCP Dev Summit Toronto, Mon 5 Oct 2026

Session: "From Zero to Production MCP Server: Turn Any API Into an Agent Tool".
10:50 to 12:15, University room, 85 minutes. Minute-by-minute flow: [RUNBOOK.md](RUNBOOK.md).

1. [Slides outline](#1-slides-outline)
2. [Fallback plan](#2-fallback-plan)
3. [Videos to record](#3-videos-to-record)
4. [Show-morning checklist](#4-show-morning-checklist)

---

## 1. Slides outline

Keep slides to the frame around the live build; the code is the content.

| # | Slide | Content | Visual |
| --- | --- | --- | --- |
| 1 | Title | Session title, name, MCP Dev Summit Toronto 2026 | Repo QR (small, bottom right) |
| 2 | The problem | Every company has internal APIs. Agents need them. A naive wrapper leaks data, trusts the model and falls over. | Three red marks on a "wrapper" box |
| 3 | The pattern | An MCP server in front of the internal API: identity in, policy in code, minimum data out | Agent → MCP server → internal API |
| 4 | What changed in MCP 2026-07-28 | Stateless (no initialize), multi round-trip confirmation (`InputRequiredResult`), CIMD replaces dynamic registration, Roots/Sampling/Logging deprecated | Four tiles, one per change |
| 5 | Today's showcase | Fictional Toronto used-car dealer, synthetic data (40 cars, 20 leads). The dealer is the showcase; the patterns are the point. | Dealer card |
| 6 | Architecture | Where we end up: API Management front door, private network, private Key Vault and ACR | `docs/architecture.svg` |
| 7 | The build plan | Stage 0 to 5, one production lesson each (see the table below) | Stage ladder |
| | **Live build** | Stages 0 to 5 | Editor + terminal |
| 8 | From commit to Azure | PR checks, build once, promote the same digest, OIDC (no secrets) | Pipeline strip from the architecture page |
| 9 | Finale | VS Code + Copilot, real Entra sign-in, $900 refused | Live |
| 10 | Production checklist | Identity, least privilege, secrets, tool quality, failure and operations | `docs/CHECKLIST.md` as 5 columns |
| 11 | Take it home | Repo QR, feedback QR, "Questions?" | Two QR codes |
| B1 | Backup: enterprise Q&A | README section 10 headlines | Text |
| B2 | Backup: hardening backlog | README section 9 | Table |

Stage ladder for slide 7:

| Stage | Adds | Production lesson |
| --- | --- | --- |
| 0 | Empty file | An MCP server is a thin, owned layer in front of the API |
| 1 | `search_inventory`, `get_vehicle` | The naive version leaks data and trusts input |
| 2 | Typed inputs, output schemas, `quote_price` | Business math in code; schemas are the contract |
| 3 | Entra auth, caller identity, masking | Identity from the token; minimum data out |
| 4 | Scope gates, policy, confirmation | Least privilege; humans approve costly actions |
| 5 | Timeouts, retries, audit, rate limit, deploy | Fail fast, retry reads only, trace every call |

QR codes:

- **Repo:** `https://github.com/hkaanturgut/zero-to-production-mcp` (works only once the repo is public).
- **Feedback:** get the session feedback link from the organizers; don't guess it.

No em dashes on slides.

---

## 2. Fallback plan

Decide in under 30 seconds, say what you're doing, and keep teaching. The audience remembers the lesson,
not the glitch.

| What fails | Signal | Fallback |
| --- | --- | --- |
| Venue Wi-Fi | `curl` hangs, npm/azd time out | Phone hotspot. Stages 0 to 4 run fully offline on localhost. Cloud steps → videos V1 to V3. |
| A paste or typo breaks the file | Server reload error in T2 | `cp workshop/stages/stage_N.py src/live/server.py` (reloads on save) |
| Lost in a stage | Behind the clock checkpoint | `git checkout stage-N` and continue; use the runbook's "If behind" cuts |
| MCP Inspector won't open | Browser tab blank or port busy | Restart T3 (`./scripts/demo.sh inspector <persona>`); else Inspector CLI: `npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8080/mcp --transport http --header "Authorization: Bearer $(./scripts/demo.sh token salesperson)" --method tools/list` |
| `azd deploy` slow (over 3 min) or fails | No "SUCCESS" by 12:01 | Keep going: mcpshow already runs stage 5 code from the rehearsal deploy. If mcpshow itself is down, use `dealer-spare` (mcprehearse). Show V3 for the deploy. |
| API Management gateway down | `dealer-cloud` times out; Resource Health says "being upgraded" | Switch to `dealer-spare` (mcprehearse). Say it: the Developer tier has no SLA; production uses Premium. |
| Entra sign-in in VS Code fails | Error or no browser prompt | Retry once from *MCP: List Servers > dealer-cloud > Start*; else play V1. |
| Copilot picks odd tools or wanders | Wrong car, extra calls | Use the exact prompt (V1 script); name the car ("the 2021 Tiguan"). Explain: the server enforces policy whatever the model does. |
| Manager confirmation won't render | No confirm dialog | Play V2. Point at `confirmation()` in `src/server/tools/common.py`. |
| Laptop dies | | Second device with the videos and the repo open in the browser |

---

## 3. Videos to record

Record at 1920×1080, editor font 18+, terminal 20+, notifications off. Each video ends on the result
the audience needs to see; trim dead time but don't speed up typing. Run `./scripts/preshow.sh --cloud`
before and after recording (it resets demo data and turns the manager role off).

### V1: Entra sign-in and the finale (about 90 s)

1. VS Code, repo open, Copilot Chat in **Agent** mode, no MCP server running.
2. *MCP: List Servers > dealer-cloud > Start*. Show the Microsoft sign-in and pick the account.
3. Prompt:
   > A customer wants an AWD SUV under $25,000 with under 100,000 km. Find the best match, give me the all-in price, save her as a lead (Priya Natarajan, 416-555-0142), and apply a $900 discount.
4. Approve each tool call. Must be visible: `search_inventory` → TBA-1017 (2021 Tiguan), `quote_price` → **$20,209.50**, `create_lead` with a masked phone, `apply_discount` → **"Discounts over $500 need a sales manager."**
5. Optional 10 s: a terminal with `az containerapp logs show -g rg-mcpshow -n ca-mcp-mcpshow --follow --format text | grep tool_call` showing the audit lines.

### V2: Manager confirmation (about 60 s)

1. `./scripts/manager-role.sh on`, then in VS Code sign out of the dealer-cloud account and sign back in (fresh token with `dms.manager`).
2. Prompt: "Apply a $900 discount to TBA-1017, reason: loyal customer."
3. Must be visible: the confirmation dialog ("Apply a $900.00 discount to TBA-1017? Reason: loyal customer"), **accept**, result `discount: 900`.
4. Optional second take: **decline** → "The user did not confirm. Nothing was changed."
5. Afterwards: `./scripts/manager-role.sh off`, sign out and back in, `./scripts/preshow.sh --cloud`.

### V3: `azd deploy mcp` (about 100 s)

1. Terminal at the repo root on `main` (stage 5 code), font 20+.
2. `azd deploy mcp -e mcpshow`. Keep the whole run (about 80 s); the remote ACR build is the point.
3. Then: `curl -s "$(azd env get-value MCP_URL -e mcpshow | sed 's#/mcp$##')/healthz"` → `{"status":"ok"}`, and
   `curl -si -X POST -H "Content-Type: application/json" -d "{}" "$(azd env get-value MCP_URL -e mcpshow)" | grep -i www-authenticate` → `resource_metadata=...`.

---

## 4. Show-morning checklist

### T minus 2 h (hotel)

- [ ] `./scripts/preshow.sh` → **ALL GREEN** (tools, envs, manager role off, demo data reset, real-token call, git clean, Inspector cached, rehearse 34/34)
- [ ] `git checkout stage-0`; `git status` clean
- [ ] Videos V1 to V3 on the laptop **and** a second device, playable offline
- [ ] Charger, USB-C to HDMI adapter, clicker, phone hotspot tested

### T minus 45 min (room)

- [ ] Venue Wi-Fi and hotspot both work: `curl -s "$(azd env get-value MCP_URL -e mcpshow | sed 's#/mcp$##')/healthz"`
- [ ] Display: mirror mode, 1920×1080; check the back row can read the editor
- [ ] VS Code: zoom (Cmd + =) until 18+ px effective, terminal 20+, minimap off, Copilot signed in, Agent mode selected
- [ ] Browser for Inspector at 150% zoom; no personal tabs, bookmarks bar hidden
- [ ] Do Not Disturb on; Slack, Mail, Teams closed; desktop clean
- [ ] Terminals open per the runbook layout (T1 DMS, T2 live, T3 Inspector, T4 free with `.env` loaded)

### T minus 10 min

- [ ] `./scripts/preshow.sh --cloud` one last time (resets show data; about 1 min)
- [ ] Editor shows `src/live/server.py` (stage 0) and `workshop/snippets/stage_1.txt`
- [ ] Water, timer visible (checkpoints: stage 3 by 11:22, stage 5 by 11:52, deploy started by 11:58)

### After the talk (Monday afternoon)

- [ ] Remove the Azure CLI pre-authorization from `infra/modules/entra.bicep`
- [ ] `azd down --purge` on mcpdev, mcpshow and mcprehearse; delete the `dealer-mcp-*` Entra apps and the CI app if no longer needed
