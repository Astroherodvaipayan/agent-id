import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from app import agntid_gate as gate

class Client:
    def __init__(self, *args, **kwargs): self.called = False
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def call_tool_async(self, *args):
        self.called = True
        return SimpleNamespace(denied=False)

@asynccontextmanager
async def context(*args):
    yield

@pytest.mark.parametrize("accepted,shortlisted", [(False, True), (True, False)])
def test_task_denial_or_missing_shortlist_stops_dispatch(monkeypatch, accepted, shortlisted):
    holder = Client()
    monkeypatch.setenv("AGNTID_MCP_URL", "http://localhost:8082/mcp")
    monkeypatch.setattr(gate.agntid, "AgntidMCPClient", lambda *a, **kw: holder)
    monkeypatch.setattr(gate.agntid, "get_tools_list", lambda c: asyncio.sleep(0, result=[SimpleNamespace(name=gate.TOOL,inputSchema={'type':'object','properties':{key:{'type':kind} for key,kind in gate.runtime_tools.LEGACY_SCHEMA.items()},'required':list(gate.runtime_tools.LEGACY_SCHEMA)})]))
    monkeypatch.setattr(gate.agntid, "create_task", lambda *a: "task-1")
    monkeypatch.setattr(gate.agntid, "wrap_client", lambda c, tid: c)
    monkeypatch.setattr(gate.agntid, "task_context", context)
    monkeypatch.setattr(gate.agntid, "send_task_open_details", lambda *a: asyncio.sleep(0, result=SimpleNamespace(ok=accepted, reason="denied")))
    monkeypatch.setattr(gate.agntid, "filter_tools_for_task", lambda tools, opened: tools if shortlisted else [])
    with pytest.raises(PermissionError):
        asyncio.run(gate.protected_send("op-1", 2400000))
    assert not holder.called

def test_mcp_error_is_not_reported_as_success(monkeypatch):
    holder = Client()
    async def error_call(*args):
        return SimpleNamespace(isError=True, denied=False)
    holder.call_tool_async = error_call
    monkeypatch.setenv("AGNTID_MCP_URL", "http://localhost:8082/mcp")
    monkeypatch.setattr(gate.agntid, "AgntidMCPClient", lambda *a, **kw: holder)
    monkeypatch.setattr(gate.agntid, "get_tools_list", lambda c: asyncio.sleep(0, result=[SimpleNamespace(name=gate.TOOL,inputSchema={'type':'object','properties':{key:{'type':kind} for key,kind in gate.runtime_tools.LEGACY_SCHEMA.items()},'required':list(gate.runtime_tools.LEGACY_SCHEMA)})]))
    monkeypatch.setattr(gate.agntid, "create_task", lambda *a: "task-1")
    monkeypatch.setattr(gate.agntid, "wrap_client", lambda c, tid: c)
    monkeypatch.setattr(gate.agntid, "task_context", context)
    monkeypatch.setattr(gate.agntid, "send_task_open_details", lambda *a: asyncio.sleep(0, result=SimpleNamespace(ok=True)))
    monkeypatch.setattr(gate.agntid, "filter_tools_for_task", lambda tools, opened: tools)
    with pytest.raises(RuntimeError, match="MCP tool returned an error"):
        asyncio.run(gate.protected_send("op-1", 2400000))
