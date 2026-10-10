from mcp.server.fastmcp import FastMCP
import os
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from .core import send_nonbinding_proposal as send
from .local_config import load_local_config

mcp = FastMCP("campaign-email")
# Approved Docker-to-host connection; keep loopback binding and default Origin checks.
PORT = int(os.getenv("MCP_PORT", "8766"))
mcp.settings.transport_security.allowed_hosts.append(f"host.docker.internal:{PORT}")

@mcp.tool()
def send_nonbinding_proposal(operation_id: str, amount_paise: int) -> dict:
    """Send one approved nonbinding proposal. Recipient and text are owned by the backend."""
    return send(operation_id, amount_paise)

@mcp.tool()
def send_creator_proposal(negotiation_id: str, operation_id: str, amount_paise: int) -> dict:
    """Dispatch one exact approved creator proposal; backend owns recipient, phase, text and aggregate budget."""
    from .negotiations import send_creator_proposal as dispatch
    return dispatch(negotiation_id, operation_id, amount_paise)

if __name__ == "__main__":
    load_local_config()
    token = os.getenv("AGNTID_TOOL_TOKEN")
    if not token:
        raise SystemExit("AGNTID_TOOL_TOKEN is required; MCP server fails closed")
    app = mcp.streamable_http_app()
    class RuntimeAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if not secrets.compare_digest(token, supplied):
                return JSONResponse({"detail": "runtime transport authorization required"}, status_code=401)
            return await call_next(request)
    app.add_middleware(RuntimeAuth)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
