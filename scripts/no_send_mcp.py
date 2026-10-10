"""Isolated AgntID policy-test MCP server. No application or mail imports."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP


PORT = int(os.environ.get("AGNTID_NO_SEND_PORT", "8777"))
mcp = FastMCP("campaign-email-no-send")
mcp.settings.transport_security.allowed_hosts.append(f"host.docker.internal:{PORT}")
LEDGER = Path(os.environ.get("AGNTID_NO_SEND_LEDGER", "/tmp/campaign-agntid-no-send.jsonl"))
MARKER = "campaign-email-no-send-v1"


def record(tool: str, arguments: dict) -> dict:
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "arguments": arguments,
        "effect": "ledger_only_no_email",
    }
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
    return {"ok": True, "no_send": True, "tool": tool, "arguments": arguments}


@mcp.tool()
def confirm_no_send_handler() -> dict:
    """Identify this isolated handler before any proposal policy probe runs."""
    return {"ok": True, "marker": MARKER, "email_capable": False}


@mcp.tool()
def send_nonbinding_proposal(operation_id: str, amount_paise: int) -> dict:
    """Record a proposal policy test. Never sends email."""
    return record("send_nonbinding_proposal", {"operation_id": operation_id, "amount_paise": amount_paise})


@mcp.tool()
def send_creator_proposal(negotiation_id: str, operation_id: str, amount_paise: int) -> dict:
    """Record a creator proposal policy test. Never sends email."""
    return record("send_creator_proposal", {"negotiation_id": negotiation_id, "operation_id": operation_id, "amount_paise": amount_paise})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=PORT)
