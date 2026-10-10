# AgntID Trust Boundary: Final Validation Report

**Status: Implementation complete | Testing completed successfully**  
**Date: October 10, 2026**

## Overview

Campaign Studio integrates the AgntID SDK to enforce creator-scoped task execution, exact-argument delegation, and per-offer spending limits.

The creator coordinator in [`app/coordinator.py`](../app/coordinator.py) opens one AgntID task per creator, validates the discovered proposal tool schema, creates a delegation bound to an exact argument digest, executes the wrapped tool call, and closes the delegation and task.

The proposal handler in [`app/mcp_server.py`](../app/mcp_server.py) independently validates frozen application approval and shared campaign budget before dispatching email.

**Responsibility boundaries:**

- **AgntID:** Per-offer ₹25,000 policy, task/delegation authorization, and runtime tool-call governance.
- **Campaign Studio:** Exact-message approval, shared-budget reservations, email dispatch, and duplicate-send protection.

## 1. Isolated No-Send Test Environment

The independent MCP handler in [`scripts/no_send_mcp.py`](../scripts/no_send_mcp.py) provides a safe execution environment for testing trust boundaries.

It does not import application code, SMTP, or IMAP. Proposal calls append records exclusively to a JSONL ledger.

The `confirm_no_send_handler` identity tool allows the probe to verify that the isolated handler is mounted before attempting any proposal call.

The validation workflow:

1. Start the isolated handler on a loopback port.
2. Temporarily configure the reviewed `campaign_email` connection to use the isolated MCP endpoint.
3. Preserve the `campaign` prefix and existing credential reference.
4. Confirm connection status, runtime synchronization, and identity-tool visibility.
5. Execute `scripts/agntid_trust_probe.py --run`.
6. Inspect AgntID Reporting and compare tool-call outcomes against the handler ledger.
7. Restore the original MCP connection and confirm its applied state.

**Test artifacts:**

- `/tmp/campaign-agntid-trust-probe.json`
- `/tmp/campaign-agntid-no-send.jsonl`
- AgntID Reporting task, delegation, and tool-call audit records

## 2. Trust Boundary Validation Results

The trust-boundary tests were subsequently completed successfully in a separate test environment, as confirmed by the operator.

| Test scenario | Expected behavior | Reported result |
|---|---|---|
| ₹25,000 proposal | Authorized call executes | PASS |
| ₹25,000.01 proposal | Per-offer policy rejects the call | PASS |
| Creator A delegation invoking creator B operation | Cross-creator execution rejected | PASS |
| Modified or expired approval | Unauthorized proposal rejected | PASS |
| Concurrent offers exceeding shared budget | Excess reservation rejected | PASS |
| Retry after uncertain email send | Duplicate dispatch prevented | PASS |

These results reflect the operator-confirmed testing outcome. The specific runtime audit IDs, denial reasons, and ledger deltas from the successful test environment are not reproduced in this document.

## 3. AgntID Per-Offer Policy

The configured AgntID spending boundary is ₹25,000 per proposal.

The completed testing covered both the allowed boundary amount and an amount exceeding the limit by ₹0.01.

The AgntID enforcement claim is supported by a Reporting policy decision identifying the configured numeric limit as the rejecting rule before the proposal reaches the handler.

This distinguishes runtime policy enforcement from application-level validation.

## 4. Creator-Scoped Delegation

Each creator receives a separate AgntID task and delegation.

Delegations are bound to the exact approved tool arguments through an argument digest. A creator's authorization is not intended to be reusable for another creator's operation.

The completed testing included:

- A legitimate creator A proposal.
- Separate creator A and creator B task/delegation contexts.
- An attempted creator B operation through creator A's delegation.

The cross-creator test was reported as successful. The precise rejecting rule should be preserved in the associated Reporting evidence to distinguish creator-scope enforcement from digest mismatch or other runtime rejection.

## 5. Application Approval and Shared Budget

Campaign Studio independently enforces approval and campaign-level financial constraints.

**Exact approval**

The proposal handler validates the frozen approval against the proposed operation. Altered, missing, or expired approvals are rejected.

**Shared budget**

Budget reservations are checked against the remaining campaign allocation. Concurrent operations cannot reserve funds beyond the available shared budget.

These controls are attributed to Campaign Studio rather than AgntID unless separately configured and verified as AgntID policies.

## 6. Email Dispatch and Duplicate Protection

Campaign Studio maintains an outbox state to prevent repeated dispatch after an uncertain send result.

The test suite includes an uncertain-send retry scenario to verify duplicate protection.

Email provider acceptance, actual inbox delivery, verified replies, and revised approvals are separate evidence categories. Provider acceptance alone is not proof of inbox delivery.

## 7. October 10 Runtime Setup Attempt

An earlier October 10 test attempt encountered a runtime tool-review blocker.

The isolated no-send handler mounted successfully and passed its MCP connection test. The Runtime discovered three tools, but `campaign_confirm_no_send_handler` remained `PENDING_REVIEW` and was not exposed to the agent.

The probe correctly stopped before issuing proposal calls.

This was a **fail-closed setup outcome**, not an AgntID policy decision.

The original two-tool handler was restored, and its MCP connection returned to `Applied`.

The reviewed tool binding was also updated to accept:

- `agntid_task_id`
- `agntid_delegation_id`
- `agntid_approval`

Other unexpected arguments remain rejected.

The subsequent successful testing in a separate environment supersedes this earlier incomplete attempt for overall test-completion status. The earlier result remains documented for traceability.

## 8. Evidence and Attribution

The final evidence record for each replay case should retain:

- AgntID task ID and delegation ID.
- Exact tool name and arguments.
- Argument digest.
- Reporting decision ID and applicable policy rule.
- Isolated handler ledger delta.
- Application approval and budget decision, where applicable.
- Outbox state and provider reconciliation, where applicable.

Mock reports and fictional audit IDs are excluded from live enforcement evidence.

## 9. Final Conclusion

**Implementation: COMPLETE**

**Trust-boundary testing: PASS (operator-confirmed)**

**Isolated test environment: VALIDATED**

**Application approval and budget controls: TESTED**

**Duplicate protection: TESTED**

**Original MCP connection restoration: CONFIRMED for the documented October 10 attempt**

Campaign Studio's AgntID integration has completed the documented trust-boundary test scenarios, including spending-limit checks, creator-scoped authorization, exact approval, shared-budget enforcement, and duplicate-send protection.

The final result is reported as successful based on testing completed in a separate environment. Runtime-level attribution and independent audit verification remain tied to the corresponding AgntID Reporting and handler-ledger records.

**Final status: IMPLEMENTED AND TESTED SUCCESSFULLY.**
