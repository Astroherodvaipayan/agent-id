import asyncio
import json
from types import SimpleNamespace

import pytest

from scripts import agntid_trust_probe as probe
from scripts import no_send_mcp


def test_isolated_handler_records_only_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "calls.jsonl"
    monkeypatch.setattr(no_send_mcp, "LEDGER", ledger)
    assert no_send_mcp.confirm_no_send_handler()["email_capable"] is False
    result = no_send_mcp.send_creator_proposal("creator-a", "op-a", 2_500_000)
    assert result["no_send"] is True
    assert json.loads(ledger.read_text())["effect"] == "ledger_only_no_email"
    assert json.loads(ledger.read_text())["arguments"] == {
        "negotiation_id": "creator-a", "operation_id": "op-a", "amount_paise": 2_500_000}


@pytest.mark.parametrize("result,status", [
    (SimpleNamespace(denied=True, isError=False, structuredContent={"reason": "policy"}), "runtime_denied"),
    (SimpleNamespace(denied=False, isError=True, structuredContent={}), "mcp_error_or_runtime_error"),
    (SimpleNamespace(denied=False, isError=False, structuredContent={"no_send": True}), "no_send_handler_reached"),
    (SimpleNamespace(denied=False, isError=False, structuredContent={}), "inconclusive"),
])
def test_probe_does_not_mislabel_sdk_result(result, status):
    assert probe.decision(result)["status"] == status


def test_probe_fails_before_proposal_when_no_send_identity_missing(tmp_path, monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            self.calls = []
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def call_tool_async(self, name, args):
            self.calls.append(name)
            raise AssertionError("No tool call should occur")

    client = Client()
    monkeypatch.setattr(probe.agntid, "AgntidMCPClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(probe.agntid, "get_tools_list", lambda _: asyncio.sleep(0, result=[{
        "name": probe.TOOL,
        "inputSchema": {"type": "object", "properties": {
            name: {"type": kind} for name, kind in probe.runtime_tools.CREATOR_SCHEMA.items()},
            "required": list(probe.runtime_tools.CREATOR_SCHEMA)}}]))
    with pytest.raises(PermissionError, match="No-send identity tool absent"):
        asyncio.run(probe.run(tmp_path / "ledger.jsonl"))
    assert client.calls == []
