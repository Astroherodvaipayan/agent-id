"""Reproducible AgntID boundary probe against the isolated no-send MCP handler.

This script never connects to SMTP or the application database. It fails closed unless
the Runtime exposes and answers the no-send identity tool. A result from the SDK is
not a Reporting receipt; correlate the emitted IDs in AgntID Reporting separately.
"""

import argparse
import asyncio
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import agntid

from app import runtime_tools


def response_data(result):
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", []):
        value = getattr(block, "text", None)
        if value:
            try:
                data = json.loads(value)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    return {}


def control_accepted(result):
    data = response_data(result)
    return not (getattr(result, "denied", False) or getattr(result, "isError", False)
                or data.get("denied") is True or data.get("isError") is True) and (
        data.get("ok") is True or data.get("accepted") is True or data.get("allowed") is True)
TOOL = runtime_tools.CREATOR_TOOL
IDENTITY_TOOL = "campaign_confirm_no_send_handler"
MARKER = "campaign-email-no-send-v1"


def decision(result):
    data = response_data(result)
    denied = bool(getattr(result, "denied", False) or data.get("denied") is True)
    error = bool(getattr(result, "isError", False) or data.get("isError") is True)
    if denied:
        status = "runtime_denied"
    elif error:
        status = "mcp_error_or_runtime_error"
    elif data.get("no_send") is True:
        status = "no_send_handler_reached"
    else:
        status = "inconclusive"
    return {"status": status, "reason": data.get("reason") or data.get("error"), "handler_reached": data.get("no_send") is True}


def ledger_count(path):
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())


async def probe_call(client, *, creator, arguments, approved_arguments, ledger):
    agent = os.getenv("AGNTID_AGENT_ID", "campaign-coordinator")
    acting = os.getenv("AGNTID_NEGOTIATOR_AGENT_ID", "creator-negotiator")
    user = os.getenv("AGNTID_USER_ID", "brand-operator")
    task_id = agntid.create_task(agent, user, f"No-send AgntID trust probe for {creator}; only {TOOL} is delegated.")
    delegation_id = secrets.token_hex(12)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    operation = approved_arguments["operation_id"]
    prompt = f"Inspect one approved no-send proposal for creator {creator}, operation {operation}. Do not send email."
    row = {"creator": creator, "task_id": task_id, "delegation_id": delegation_id, "tool": TOOL,
           "approved_arguments": approved_arguments, "attempted_arguments": arguments,
           "reporting_audit_id": None, "ledger_before": ledger_count(ledger)}
    async with agntid.task_context(client, task_id):
        opened = await agntid.send_task_open_details(client, task_id, agent, user, prompt)
        row["task_open"] = {"accepted": bool(opened.ok), "reason": getattr(opened, "reason", None)}
        if not opened.ok:
            row["decision"] = {"status": "task_denied"}
            return row
        context = agntid.DelegationContext(
            delegation_id=delegation_id,
            parent_agent_id=agent,
            acting_agent_id=acting,
            delegated_intent=agntid.DelegatedIntent(
                text=prompt, action=TOOL, resource=creator,
                scope={"negotiation_id": creator, "operation_id": operation},
                constraints=("one creator", "exact approved arguments", "no email"),
                source="isolated_no_send_probe"),
            tool_allowlist=(TOOL,),
            approval=agntid.ApprovalEvidence(
                required=True, decision="approved", approver_id="probe-operator",
                decision_id=operation, operation_id=operation,
                source="isolated_no_send_probe", tool_name=TOOL,
                arguments_digest=agntid.arguments_digest(approved_arguments),
                expires_at=expires))
        acknowledgement = await agntid.send_delegation_open(client, task_id, context)
        row["delegation_open"] = {"accepted": control_accepted(acknowledgement),
                                  "response": response_data(acknowledgement)}
        if not row["delegation_open"]["accepted"]:
            row["decision"] = {"status": "delegation_denied_or_unverified"}
            return row
        try:
            result = await agntid.wrap_client(client, task_id, delegation_id).call_tool_async(TOOL, arguments)
            row["decision"] = decision(result)
        except Exception as exc:
            row["decision"] = {"status": "sdk_exception", "reason": str(exc)}
        finally:
            await agntid.send_delegation_close(client, task_id, delegation_id, status="completed")
    row["ledger_after"] = ledger_count(ledger)
    row["handler_invocations"] = row["ledger_after"] - row["ledger_before"]
    return row


async def run(ledger):
    async with agntid.AgntidMCPClient(runtime_tools.runtime_url(), access_token=os.getenv("AGNTID_ACCESS_TOKEN") or None) as client:
        visible = await agntid.get_tools_list(client)
        runtime_tools.validate_binding(visible, TOOL, runtime_tools.CREATOR_SCHEMA)
        if IDENTITY_TOOL not in {runtime_tools.name(tool) for tool in visible}:
            raise PermissionError("No-send identity tool absent from Runtime; no proposal call attempted")
        marker_result = await client.call_tool_async(IDENTITY_TOOL, {})
        marker = response_data(marker_result)
        if marker.get("marker") != MARKER or marker.get("email_capable") is not False:
            raise PermissionError("No-send identity not verified; no proposal call attempted")

        nonce = secrets.token_hex(8)
        a = {"negotiation_id": f"probe-a-{nonce}", "operation_id": f"probe-a-op-{nonce}", "amount_paise": 2_500_000}
        over = dict(a, operation_id=f"probe-over-op-{nonce}", amount_paise=2_500_001)
        b = {"negotiation_id": f"probe-b-{nonce}", "operation_id": f"probe-b-op-{nonce}", "amount_paise": 1_000}
        cases = [
            ("creator_a_at_limit", a["negotiation_id"], a, a),
            ("creator_a_over_limit", a["negotiation_id"], over, over),
            ("creator_b_approved", b["negotiation_id"], b, b),
            ("creator_a_attempts_b_operation", a["negotiation_id"], b, a),
        ]
        rows = []
        for name, creator, attempted, approved in cases:
            row = await probe_call(client, creator=creator, arguments=attempted,
                                   approved_arguments=approved, ledger=ledger)
            row["case"] = name
            rows.append(row)
        return {"kind": "real_runtime_no_send_probe", "runtime_url": runtime_tools.runtime_url(),
                "handler_marker": MARKER, "reporting_correlation": "pending_manual_review",
                "claims": {"numeric_policy": "unverified_until_reporting_correlated",
                           "creator_isolation": "unverified_until_denial_reason_correlated"}, "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Execute against the connected Runtime after mounting the isolated handler")
    parser.add_argument("--ledger", type=Path, default=Path("/tmp/campaign-agntid-no-send.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/campaign-agntid-trust-probe.json"))
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; first mount and verify scripts/no_send_mcp.py in the Runtime")
    result = asyncio.run(run(args.ledger))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
