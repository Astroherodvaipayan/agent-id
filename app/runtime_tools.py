"""Exact reviewed runtime tool bindings. No prefix/suffix discovery guesses."""
import os
from urllib.parse import urlparse

DEFAULT_RUNTIME_URL='http://127.0.0.1:8082/mcp'
CREATOR_TOOL='campaign_send_creator_proposal'  # Actual runtime discovery supplied by setup worker.
LEGACY_TOOL='campaign_send_nonbinding_proposal'  # Verified runtime discovery.
CREATOR_SCHEMA={'negotiation_id':'string','operation_id':'string','amount_paise':'integer'}
LEGACY_SCHEMA={'operation_id':'string','amount_paise':'integer'}


def runtime_url():
    value=os.getenv('AGNTID_MCP_URL') or DEFAULT_RUNTIME_URL
    parsed=urlparse(value)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.port!=8082 or parsed.path!='/mcp' or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Configure the reviewed local Runtime MCP endpoint on port 8082')
    return value


def _field(tool,name):
    return tool.get(name) if isinstance(tool,dict) else getattr(tool,name,None)


def name(tool):
    return _field(tool,'name')


def validate_binding(tools,selected,expected):
    matches=[tool for tool in tools if name(tool)==selected]
    if len(matches)!=1:raise PermissionError('Exact approved runtime tool missing or ambiguous')
    schema=_field(matches[0],'inputSchema') or _field(matches[0],'input_schema')
    if not isinstance(schema,dict) or schema.get('type')!='object':raise PermissionError('Runtime tool input schema is missing or invalid')
    properties=schema.get('properties');required=schema.get('required')
    if not isinstance(properties,dict) or not isinstance(required,list) or set(required)!=set(expected):raise PermissionError('Runtime tool arguments differ from the reviewed backend action')
    if not set(properties)<=set(expected)|{'_task_id','_delegation_id','_approval'}:raise PermissionError('Runtime tool exposes unapproved arguments')
    for field,kind in expected.items():
        if not isinstance(properties.get(field),dict) or properties[field].get('type')!=kind:raise PermissionError('Runtime tool argument type differs from the reviewed backend action')
    return selected


def creator_tool():
    selected=os.getenv('AGNTID_CREATOR_TOOL') or CREATOR_TOOL
    # Original unprefixed name is usable only when explicitly selected for a standalone test server.
    if selected not in (CREATOR_TOOL,'send_creator_proposal'):raise ValueError('Unreviewed creator runtime tool name')
    return selected


def legacy_tool():
    selected=os.getenv('AGNTID_LEGACY_TOOL') or LEGACY_TOOL
    if selected not in (LEGACY_TOOL,'send_nonbinding_proposal'):raise ValueError('Unreviewed legacy runtime tool name')
    return selected
