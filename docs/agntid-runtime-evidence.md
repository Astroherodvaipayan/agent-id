# AgntID runtime evidence: three-call record

**Status: awaiting proposal-call evidence.** This page is the public record for the three decisive calls. It does not count configured policies, local tests, or an SDK response alone as AgntID enforcement.

## What a complete proof looks like

All three calls must use the same isolated, no-email MCP handler. Publish a redacted AgntID Reporting export or screenshot for each decision and the corresponding handler ledger lines. Join them by the exact tool arguments, task ID, delegation ID, timestamp, and Reporting audit/decision ID. Keep the full unredacted records private.

| Call | AgntID Reporting proof | Handler-ledger proof | Current record |
| --- | --- | --- | --- |
| Approved ₹25,000 offer (`amount_paise=2500000`) | `ALLOW`, proposal tool name, task ID, delegation ID, decision ID, applied policy | Exactly one line for its unique operation ID | **Pending** |
| ₹25,000.01 offer (`amount_paise=2500001`) | `DENY`, the **amount-policy rule** and its actual reason, task ID, delegation ID, decision ID | Zero lines for its unique operation ID | **Pending** |
| Creator A worker attempts creator B's operation | `DENY`, the **creator-scope rule** and its actual reason, A's task/delegation IDs, B's attempted negotiation/operation IDs, decision ID | Zero lines for B's attempted operation | **Pending** |

For the creator call, a denial caused by an approval digest mismatch, missing delegation, malformed arguments, or Campaign Studio's backend does **not** prove AgntID creator-scope enforcement. Record the actual rule, even if it shows that this boundary remains unenforced by AgntID.

Each completed row should include a small redacted record in this shape, using **real** values from the same run:

```text
case: approved_at_limit | over_limit | creator_a_attempts_b
UTC timestamp: [from Reporting]
tool: campaign_send_creator_proposal
task_id: [real task ID]
delegation_id: [real delegation ID]
operation_id: [real unique operation ID]
negotiation_id: [real creator-scoped ID]
amount_paise: [2500000 or 2500001 or attempted amount]
AgntID outcome: [ALLOW or DENY]
AgntID decision/audit ID: [real ID]
AgntID policy and exact reason: [verbatim redacted reason]
handler ledger lines for operation_id: [0 or 1]
source: [link to redacted Reporting export] · [link to redacted ledger excerpt]
```

## Controlled inbox receipt

**Pending public evidence link.** For the legitimate flow, link a redacted inbox screenshot or exported message with delivery timestamp, message ID, and a reply referring to that same proposal. Link the app's approval record showing the exact recipient, wording, and amount, and the new approval after the reply changed the proposal. Hide tokens and personal addresses before publishing. A provider `accepted` response by itself does not prove inbox receipt.

## Recorded setup attempt — 10 October 2026

The isolated handler passed its connection test and the runtime discovered three tools. The no-send identity action remained `PENDING_REVIEW` and was not agent-visible, so the [probe](../scripts/agntid_trust_probe.py) stopped before any proposal call. No entries from this attempt satisfy the three rows above. The original two-tool campaign handler was restored and the MCP connection showed `Applied`. See the [trust-probe guide](agntid-trust-probe.md) for the setup and repeatable procedure.
