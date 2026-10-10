import pytest
from app import runtime_tools as rt

def tool(name=None,extra=None):
    properties={k:{'type':v} for k,v in rt.CREATOR_SCHEMA.items()}
    properties.update(extra or {})
    return {'name':name or rt.CREATOR_TOOL,'inputSchema':{'type':'object','properties':properties,'required':list(rt.CREATOR_SCHEMA)}}

def test_verified_default_endpoint(monkeypatch):
    monkeypatch.delenv('AGNTID_MCP_URL',raising=False)
    assert rt.runtime_url()=='http://127.0.0.1:8082/mcp'

@pytest.mark.parametrize('value',['https://example.com/mcp','http://127.0.0.1:8766/mcp','http://user:pass@127.0.0.1:8082/mcp'])
def test_unreviewed_endpoint_rejected(monkeypatch,value):
    monkeypatch.setenv('AGNTID_MCP_URL',value)
    with pytest.raises(ValueError):rt.runtime_url()

def test_exact_binding_and_no_recipient_body():
    assert rt.validate_binding([tool()],rt.CREATOR_TOOL,rt.CREATOR_SCHEMA)==rt.CREATOR_TOOL
    for tools in ([tool('other_'+rt.CREATOR_TOOL)],[tool(),tool()],[tool(extra={'recipient':{'type':'string'}})]):
        with pytest.raises(PermissionError):rt.validate_binding(tools,rt.CREATOR_TOOL,rt.CREATOR_SCHEMA)

def test_both_verified_aliases(monkeypatch):
    monkeypatch.delenv('AGNTID_LEGACY_TOOL',raising=False)
    assert rt.legacy_tool()=='campaign_send_nonbinding_proposal'
    monkeypatch.setenv('AGNTID_CREATOR_TOOL','arbitrary_send')
    with pytest.raises(ValueError):rt.creator_tool()
