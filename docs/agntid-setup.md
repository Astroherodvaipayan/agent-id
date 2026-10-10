# AgntID setup for the campaign demo

This is an operator checklist. No runtime, portal policy, token, SMTP account, or model credential is configured by the repository. Do not paste secrets into chat or commit them.

## 1. Start and connect Runtime 2.0.0

On the machine that can run Docker, obtain the official `docker-compose.yml` from `AGNTID-AI/agntid-python` and run `docker compose up -d`; check `docker compose ps` until both services are healthy. The official images are public. Open `http://localhost:8080`. In the AgntID portal, open **Runtimes → Add Runtime**, generate a bootstrap token, and enter it in the local runtime UI. Verify **Operational** and **Connected**. The current Codex executor could not access the Docker socket, so this step is unverified.

In the runtime **Setup** tab, review the protection profile and confirm **5 of 5** checks and **Runtime sync: Applied**. The profile must allow the reviewed write action; a restrictive profile can hide the tool before policy evaluation.

## 2. Connect the campaign MCP server

Install the project locally and configure a strong, operator-owned `AGNTID_TOOL_TOKEN` in the MCP server process. The server refuses to start without it and listens on `127.0.0.1:8766` by default. Run `python -m app.mcp_server`. A containerized runtime cannot reach a host service through its own `127.0.0.1`; choose a runtime-reachable, appropriately isolated address before changing the bind host. Do not expose the MCP endpoint publicly.

In the portal open **Runtimes → [your runtime] → Operations → MCP → Servers → Add MCP**. Use **Remote HTTP** with the runtime-reachable MCP URL. Configure the connection credential as **bearer_token** backed by a runtime-host environment variable holding the same token; do not paste the token into the portal form. Use a stable server ID such as `campaign_email`, then **Test Connection** and **Save MCP**. Confirm **Apply: APPLIED**, discovered tool count, and `send_nonbinding_proposal` under **Access Control → Tools**. Review and enable the action as appropriate.

The shared transport token limits who can call the tool server, but possession of that token alone does not cryptographically prove traversal through AgntID. Keep it only in the runtime-host environment and tool-server process, never in the browser, agent prompt, model state, or app API environment. Use network isolation in addition to the token.

## 3. Configure the numeric policy

Open **Access Control → Access Policies → campaign_email server → send_nonbinding_proposal → Baseline Allow Policy**. Set an inclusive input maximum for `amount_paise` of **2,500,000**. The backend has a separate 5,000,000-paise safety ceiling, so a 3,500,000-paise diagnostic should reach AgntID's numeric policy if intent/task/tool visibility permits it. Save and wait for **Runtime sync: Applied**. Do not represent a backend rejection or an intent denial as proof of the numeric policy.

Do not claim that this numeric policy enforces recipient, package, currency, wording, or thread routing. Those are backend-owned and require separate tests. The configured portal policy and its application state must be visually verified in the connected runtime.

## 4. Check the protected path without mail

First verify task-open acceptance, contextual tool shortlisting and the `send_nonbinding_proposal` tool through the official SDK. A missing or empty task shortlist stops dispatch. For a 3,500,000-paise protected diagnostic, use an isolated no-send ledger handler or other approved harness so the SMTP handler is never reached. Check **Reporting** for an actual policy-denied event and correlate task and tool details. Then test the 2,500,000/2,500,001 inclusive boundary in the same no-send harness. The local tests do not establish these portal results.

After operator approval for controlled-inbox mail, a fresh 2,400,000-paise task can send one nonbinding proposal. Reconcile provider acceptance, actual inbox receipt and reply as separate evidence. Never retry an SMTP `unknown` outcome blindly. An AgntID output withholding decision may arrive after a side effect; consult the outbox before deciding what happened.

## 5. Configure the model and mail separately

The brand app expects `GEMINI_API_KEY` and `GEMINI_MODEL`; you will supply the key in the local process environment. The Gemini model is used for reviewable drafting, not for authorization. The AgntID standard intent engine can check call alignment; it does not itself provide the model-driven shortlist/output protection associated with a healthy portal LLM credential. Add such a credential only if your selected AgntID flow requires it, then verify that it is healthy. A configured Gemini key in this app does not automatically configure the AgntID portal.

Configure `SMTP_*` for outbound mail and `IMAP_*` for inbound receipt. SMTP alone cannot read replies. Keep the test creator address in `CREATOR_EMAIL`. Operator, runtime-tool and model credentials have different purposes and must remain separate.
