# Show prep: MCP Dev Summit Toronto, Mon 5 Oct 2026

Session: "From Zero to Production MCP Server: Turn Any API Into an Agent Tool".
University room, **60 minutes including Q&A**. Theory from the slides, hands-on in `workshop/demo.ipynb` and `workshop/azure.ipynb`; timing, setup and fallbacks: [RUNBOOK.md](RUNBOOK.md).

1. [Slides outline](#1-slides-outline)
2. [Fallback plan](#2-fallback-plan)
3. [Videos to record](#3-videos-to-record)
4. [Show-morning checklist](#4-show-morning-checklist)

---

## 1. Slides outline

Theory lives on the slides; the hands-on part lives in the notebooks, each cell with its own explanation.
The deck: `MCP-DevSummit-Toronto-Kaan-Turgut.pptx`.

| # | Slide | When | Then |
| --- | --- | --- | --- |
| 1 | From Zero to Production MCP Server (up while people arrive) | +0 | |
| 2 | About me | +0:30 | |
| 3 | Every company has APIs. Agents need them | +1 | |
| 4 | MCP sits in front of your API | +2 | |
| 5 | Why not let the agent call the API? (REST vs MCP, when function calling is enough) | +3 | |
| 6 | How MCP talks: JSON-RPC 2.0 (`tools/list`, `tools/call`, `isError` vs `error`) | +4 | proven live in `demo.ipynb` §2 |
| 7 | What changed in MCP 2026-07-28 | +5 | |
| 8 | Today's showcase: a Toronto used-car dealer | +6 | |
| 9 | Where we end up (architecture) | +7 | |
| 10 | One request, end to end | +8 | |
| 11 | Let's build it (repo QR) | +9:30 | VS Code: `demo.ipynb` §1 to §7 |
| 12 | Policy in code, not in the prompt | during stage 4 (+28) | back to `demo.ipynb` §5 |
| 13 | From commit to Azure | +43 | `azure.ipynb` §1 to §4 |
| 14 | Finale: Copilot calls our server in Azure | backup for `azure.ipynb` §4 (+48) | |
| 15 | The production checklist | +52 | |
| 16 | What to take home | +53 | |
| 17 | Thank you. Questions? | +54 | Q&A |
| 18 | Backup | Q&A | |

Stage ladder (also the first cell of `demo.ipynb`):

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

**Rule:** stages 0 to 4 and the stage 5 code are always live (localhost, no Wi-Fi). Cloud segments (production walkthrough, Entra sign-in, Copilot) are live only if `./scripts/preshow.sh --cloud` is green on the venue Wi-Fi at T minus 45 min; otherwise play V3 and V1 and say why. The organizers recommend pre-recording demos, and this covers exactly the parts that depend on the network.

Decide in under 30 seconds, say what you're doing, and keep teaching. The audience remembers the lesson,
not the glitch.

| What fails | Signal | Fallback |
| --- | --- | --- |
| Venue Wi-Fi | `curl` hangs, npm/azd time out | Phone hotspot. Stages 0 to 4 run fully offline on localhost. Cloud steps → videos V1 to V3. |
| A paste or typo breaks the file | Server reload error in T2 | `cp workshop/stages/stage_N.py src/live/server.py` (reloads on save) |
| Lost in a stage | Behind the clock checkpoint | `git checkout stage-N` and continue; use the runbook's "If behind" cuts |
| MCP Inspector won't open | Browser tab blank or port busy | Restart T3 (`./scripts/demo.sh inspector <persona>`); else Inspector CLI: `npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8080/mcp --transport http --header "Authorization: Bearer $(./scripts/demo.sh token salesperson)" --method tools/list` |
| `azd deploy` slow (over 3 min) or fails | No "SUCCESS" by +43 | Keep going: mcpshow already runs stage 5 code from the rehearsal deploy. If mcpshow itself is down, use `dealer-spare` (mcprehearse). Show V3 for the deploy. |
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
- [ ] On `main`: `./scripts/demo.sh stage 0` (stay on `main` for the whole talk)
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
- [ ] Editor shows `src/live/server.py` (stage 0)
- [ ] Water, timer visible (checkpoints: stage 3 by +18, stage 5 by +36, finale by +46, Q&A by +54)

### After the talk (Monday afternoon)

- [ ] Remove the Azure CLI pre-authorization from `infra/modules/entra.bicep`
- [ ] `azd down --purge` on mcpdev, mcpshow and mcprehearse; delete the `dealer-mcp-*` Entra apps and the CI app if no longer needed
