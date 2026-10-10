# AgntID trust boundary: runnable evidence path

The creator coordinator in [`app/coordinator.py`](../app/coordinator.py) uses the AgntID SDK to open one task per creator, check the discovered proposal tool schema, open a creator-scoped delegation with an exact argument digest, make the wrapped tool call, and close the delegation and task. The proposal handler in [`app/mcp_server.py`](../app/mcp_server.py) then checks the frozen application approval and shared budget before any email dispatch. Those checks belong to the **application**; the configured per-call amount policy belongs to **AgntID**.

## No-send boundary probe

[`scripts/no_send_mcp.py`](../scripts/no_send_mcp.py) is a separate MCP handler. It does not import the application, SMTP, or IMAP. Its proposal tools append only to a JSONL ledger. `confirm_no_send_handler` returns a fixed marker so the probe can refuse to issue proposal calls if the Runtime is still mounted to the real sender.

1. Start the isolated handler on a free loopback port, for example `AGNTID_NO_SEND_PORT=8777 .venv/bin/python scripts/no_send_mcp.py`.
2. In the AgntID portal, temporarily point the reviewed `campaign_email` connection at `http://host.docker.internal:8777/mcp`. Preserve its `campaign` prefix and existing credential reference. Confirm connection test and runtime sync. Review visibility for the harmless `campaign_confirm_no_send_handler` identity tool. **Do not run the probe while the real sender is mounted.**
3. Run `.venv/bin/python scripts/agntid_trust_probe.py --run`. The script requires the no-send marker through the real Runtime proxy before any proposal call. It writes `/tmp/campaign-agntid-trust-probe.json` and the isolated handler writes `/tmp/campaign-agntid-no-send.jsonl`.
4. In AgntID Reporting, locate each emitted task and delegation ID. Copy the tool call audit IDs and exact denial reasons into a separate evidence record. A denied SDK response alone is not proof that the numeric policy denied the call. Confirm the ledger has one entry for each allowed call and none for each denied call.
5. Restore the original MCP URL and confirm it is applied before ending the test. Stop the isolated handler.

The probe attempts ₹25,000 and ₹25,000.01, opens separate creator A and B tasks/delegations, and tries creator B's operation through creator A's delegation. It records what the Runtime and handler actually returned. If the cross-creator attempt reaches the handler, the result is a **failed isolation check**; do not report isolation as enforced. The approval digest or another runtime rule may be the actual denial reason, so inspect Reporting before attributing a denial to creator scope.

## Evidence labels

| Claim | Required evidence | Current status |
| --- | --- | --- |
| AgntID per-offer ₹25,000 boundary | Allowed ₹25,000 call, denied ₹25,000.01 call, matching Reporting policy decision, isolated ledger | Not yet recorded |
| Creator isolation | Two task/delegation IDs, A approved call, A→B denial reason and audit ID | Not yet recorded |
| Exact approval and shared budget | Application approval records and reservation tests | Local tests only |
| Email receipt and revised approval | Controlled inbox receipt, verified reply, new exact approval | Not yet recorded |
| Duplicate protection after uncertain send | Outbox state and provider reconciliation | Local tests only |

Never turn a configured policy, SDK task event, simulated test, or provider acceptance into a claim of live policy enforcement or inbox delivery. The customer-facing demo is separate from this evidence path.

## October 10 runtime attempt

The isolated no-send handler was mounted temporarily and its connection test passed. The runtime discovered three handler tools, but `campaign_confirm_no_send_handler` was classified as `PENDING_REVIEW` and was absent from the agent-visible tool list. The probe therefore stopped before issuing any proposal call. This is a **fail-closed setup result**, not evidence that the amount or creator policy allowed or denied anything. The original two-tool handler was restored and its MCP connection returned to `Applied`. The runtime tool schema also exposed `agntid_task_id`, `agntid_delegation_id`, and `agntid_approval`; the reviewed binding now accepts these AgntID metadata fields while still rejecting other unexpected arguments.
