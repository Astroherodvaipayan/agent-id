import asyncio
import pytest
from starlette.requests import Request
from mcp.server.transport_security import TransportSecurityMiddleware
from app.mcp_server import mcp

@pytest.mark.parametrize('host,origin,expected',[
    ('host.docker.internal:8766',None,None),
    ('localhost:8766',None,None),
    ('127.0.0.1:8766',None,None),
    ('host.docker.internal:8767',None,421),
    ('unapproved.test:8766',None,421),
    ('host.docker.internal:8766','http://host.docker.internal:8766',403),
])
def test_exact_host_and_unchanged_origin(host,origin,expected):
    headers=[(b'host',host.encode()),(b'content-type',b'application/json')]
    if origin:headers.append((b'origin',origin.encode()))
    request=Request({'type':'http','method':'POST','path':'/mcp','headers':headers})
    response=asyncio.run(TransportSecurityMiddleware(mcp.settings.transport_security).validate_request(request,is_post=True))
    assert (response.status_code if response else None)==expected


def test_loopback_and_original_origin_allowlist_preserved():
    assert mcp.settings.host=='127.0.0.1'
    assert mcp.settings.transport_security.enable_dns_rebinding_protection
    assert mcp.settings.transport_security.allowed_origins==['http://127.0.0.1:*','http://localhost:*','http://[::1]:*']
    assert mcp.settings.transport_security.allowed_hosts==['127.0.0.1:*','localhost:*','[::1]:*','host.docker.internal:8766']
