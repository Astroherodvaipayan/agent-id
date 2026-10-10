"""Bounded concurrent creator workers using actual AgntID task/delegation APIs."""
import asyncio
import json
import os
import secrets
import agntid
from . import negotiations, runtime_tools

TOOL=runtime_tools.CREATOR_TOOL
_lanes=asyncio.Semaphore(3)


def record(identity,operation,run,status,task=None,delegation=None,detail=''):
    c=negotiations.db()
    try:
        c.execute('INSERT OR REPLACE INTO negotiation_runs(id,negotiation_id,operation_id,task_id,delegation_id,status,detail) VALUES (?,?,?,?,?,?,?)',(run,identity,operation,task,delegation,status,detail[:2000]))
    finally:c.close()


def response_data(result):
    if isinstance(result,dict):return result
    structured=getattr(result,'structuredContent',None) or getattr(result,'structured_content',None)
    if isinstance(structured,dict):return structured
    for block in getattr(result,'content',[]):
        value=getattr(block,'text',None)
        if value:
            try:
                data=json.loads(value)
                if isinstance(data,dict):return data
            except ValueError:pass
    return {}


def control_accepted(result):
    if getattr(result,'denied',False) or getattr(result,'isError',False):return False
    data=response_data(result)
    if data.get('denied') is True or data.get('isError') is True:return False
    # Unknown acknowledgement shapes fail closed until checked against the live runtime.
    return data.get('ok') is True or data.get('accepted') is True or data.get('allowed') is True


async def worker(identity,operator):
    async with _lanes:
        try:approval=negotiations.approved_request(identity)
        except ValueError as exc:return {'negotiation_id':identity,'status':'blocked','detail':str(exc)}
        operation=approval['operation_id'];run=secrets.token_hex(12);task=None;delegation=None
        c=negotiations.db()
        try:
            if c.execute("SELECT 1 FROM negotiation_runs WHERE operation_id=? AND status IN ('denied','blocked')",(operation,)).fetchone():
                return {'negotiation_id':identity,'status':'blocked','detail':'Denied proposal needs explicit revised approval before a new task'}
        finally:c.close()
        record(identity,operation,run,'opening_task')
        payload=json.loads(approval['payload_json'])
        args={'negotiation_id':identity,'operation_id':operation,'amount_paise':approval['amount_paise']}
        agent=os.getenv('AGNTID_AGENT_ID','campaign-coordinator')
        acting=os.getenv('AGNTID_NEGOTIATOR_AGENT_ID','creator-negotiator')
        user=os.getenv('AGNTID_USER_ID','brand-operator')
        tool=runtime_tools.creator_tool()
        prompt=f"Operator {operator} requests one exact approved nonbinding creator proposal. Negotiation {identity}; operation {operation}; brief revision {payload['brief_revision']}; phase {payload['phase']}; round {payload['round']}; amount {approval['amount_paise']} INR paise. Only {tool} is delegated. Recipient, package and wording are backend-owned. No payment, contract, lock-in, recipient changes or retry after denial."
        try:
            async with agntid.AgntidMCPClient(runtime_tools.runtime_url(),access_token=os.getenv('AGNTID_ACCESS_TOKEN') or None) as client:
                visible=await agntid.get_tools_list(client)
                runtime_tools.validate_binding(visible,tool,runtime_tools.CREATOR_SCHEMA)
                task=agntid.create_task(agent,user,prompt)
                async with agntid.task_context(client,task):
                    execution=agntid.ExecutionContext(framework=agntid.FrameworkInfo(name='campaign-controller',adapter_version='1',capabilities=('deterministic_approved_dispatch',)),turn_id=operation,root_task_id=task,root_agent_id=agent,thread_id=identity,execution_plan=agntid.ExecutionPlan(plan_id=operation,actions=(agntid.PlannedAction(action_id=operation,title='Dispatch exact approved nonbinding proposal',tool_name=tool,expected_agent_id=acting,sequence=1),)),extensions={'brief_revision':payload['brief_revision'],'round':payload['round'],'payload_hash':approval['payload_hash'],'approval_expires_at':approval['expires_at'],'plan_authority':'observability only; controller enforces ordering'})
                    opened=await agntid.send_task_open_details(client,task,agent,user,prompt,execution_context=execution)
                    if not opened.ok:raise PermissionError('AgntID task rejected: '+str(opened.reason))
                    mode=os.getenv('AGNTID_DISPATCH_MODE','standard_deterministic')
                    if mode not in ('contextual','standard_deterministic'):raise PermissionError('Unreviewed dispatch mode')
                    contextual=mode=='contextual'
                    if contextual and (not getattr(opened,'intent_prepared',False) or not getattr(opened,'snapshot',None)):raise PermissionError('Prepared contextual task snapshot missing')
                    shortlist=agntid.filter_tools_for_task(visible,opened) if contextual else visible
                    if tool not in {runtime_tools.name(t) for t in shortlist}:raise PermissionError('Accepted task did not expose the creator proposal tool')
                    delegation=secrets.token_hex(12)
                    context=agntid.DelegationContext(delegation_id=delegation,parent_agent_id=agent,acting_agent_id=acting,delegated_intent=agntid.DelegatedIntent(text=prompt,action=tool,resource=identity,scope={'negotiation_id':identity,'brief_revision':payload['brief_revision'],'round':payload['round']},constraints=('one creator','exact frozen proposal','no commitments','stop on denial'),source='operator_approved_campaign'),tool_allowlist=(tool,),approval=agntid.ApprovalEvidence(required=True,decision='approved',approver_id=approval['approver'],decision_id=operation,operation_id=operation,source='backend_operator_approval',tool_name=tool,arguments_digest=agntid.arguments_digest(args),expires_at=approval['expires_at']))
                    opened_delegation=False
                    completed=False
                    try:
                        acknowledgement=await agntid.send_delegation_open(client,task,context)
                        if not control_accepted(acknowledgement):raise PermissionError('Delegation acceptance unverified or denied; no tool dispatch')
                        opened_delegation=True
                        record(identity,operation,run,'runtime_check',task,delegation,json.dumps({'dispatch_mode':mode,'model_tool_access':False,'intent_prepared':getattr(opened,'intent_prepared',None),'intent_reason':getattr(opened,'intent_reason',None),'semantic_restriction_verified':False,'execution_plan':'audit declaration only'}))
                        result=await agntid.wrap_client(client,task,delegation).call_tool_async(tool,args)
                        if getattr(result,'denied',False) or response_data(result).get('denied') is True:raise PermissionError('AgntID tool call denied; reconcile outbox if handler already ran')
                        if getattr(result,'isError',False) or response_data(result).get('isError') is True:raise RuntimeError('MCP returned error; reconcile outbox before retry')
                        completed=True
                        record(identity,operation,run,'completed',task,delegation,'SDK result is not a signed audit receipt. Correlate task and operation in Reporting.')
                        return {'negotiation_id':identity,'task_id':task,'delegation_id':delegation,'status':'completed','result':response_data(result)}
                    finally:
                        if opened_delegation:await agntid.send_delegation_close(client,task,delegation,status='completed' if completed else 'failed')
        except Exception as exc:
            state='denied' if isinstance(exc,PermissionError) else 'blocked'
            record(identity,operation,run,state,task,delegation,str(exc))
            c=negotiations.db()
            try:out=c.execute('SELECT status,message_id FROM negotiation_outbox WHERE operation_id=?',(operation,)).fetchone()
            finally:c.close()
            return {'negotiation_id':identity,'task_id':task,'delegation_id':delegation,'status':state,'detail':str(exc),'outbox':dict(out) if out else None}


async def run(identities,operator):
    if not operator.strip() or not 1<=len(identities)<=10 or len(set(identities))!=len(identities):raise ValueError('Request 1–10 unique creator lanes with an operator')
    # Preflight every approval before opening any worker. No automatic discovery or sending.
    for identity in identities:negotiations.approved_request(identity)
    results=await asyncio.gather(*(worker(identity,operator) for identity in identities))
    return {'max_concurrency':3,'results':results,'budget_enforcement':'SQLite shared reservation ledger; separate from AgntID per-call numeric policy'}
