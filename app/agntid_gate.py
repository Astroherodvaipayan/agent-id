import os
import agntid
from . import runtime_tools

TOOL = runtime_tools.LEGACY_TOOL

async def protected_send(operation_id: str, amount_paise: int):
    tool = runtime_tools.legacy_tool()
    prompt = f"Send the operator-approved nonbinding proposal for operation {operation_id} at {amount_paise} paise."
    async with agntid.AgntidMCPClient(runtime_tools.runtime_url(), access_token=os.getenv("AGNTID_ACCESS_TOKEN") or None) as client:
        visible = await agntid.get_tools_list(client)
        runtime_tools.validate_binding(visible,tool,runtime_tools.LEGACY_SCHEMA)
        task_id = agntid.create_task(os.getenv("AGNTID_AGENT_ID", "campaign-negotiator"), os.getenv("AGNTID_USER_ID", "brand-operator"), prompt)
        wrapped = agntid.wrap_client(client, task_id)
        async with agntid.task_context(client, task_id):
            opened = await agntid.send_task_open_details(client, task_id, os.getenv("AGNTID_AGENT_ID", "campaign-negotiator"), os.getenv("AGNTID_USER_ID", "brand-operator"), prompt)
            if not opened.ok:
                raise PermissionError(f"AgntID task denied: {opened.reason}")
            shortlist = agntid.filter_tools_for_task(visible, opened)
            if tool not in {runtime_tools.name(t) for t in shortlist}:
                raise PermissionError("AgntID task snapshot did not shortlist the send tool")
            result = await wrapped.call_tool_async(tool, {"operation_id": operation_id, "amount_paise": amount_paise})
            if getattr(result, "denied", False):
                raise PermissionError("AgntID denied the tool call; inspect Reporting for the policy event")
            if getattr(result, "isError", False) or (isinstance(result, dict) and result.get("isError") is True):
                raise RuntimeError("Protected MCP tool returned an error; inspect outbox before any retry")
            return {"task_id": task_id, "result": result}
