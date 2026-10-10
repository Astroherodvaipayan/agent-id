/* Operator actions only; untrusted mail and model prose never authorize dispatch. */
window.renderCreatorLanes=function(state,api,reload,toast){
 const root=document.getElementById('creatorLanes');if(!root)return;root.replaceChildren();
 const data=state.negotiation||{},campaign=state.campaign?.[0];
 const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e};
 const input=(placeholder,type='text')=>{const e=el('input');e.placeholder=placeholder;e.type=type;e.className='field';return e};
 const button=(text,action)=>{const b=el('button',text,'quiet');b.onclick=async()=>{b.disabled=true;try{await action()}catch(e){toast(e.message,true)}finally{b.disabled=false}};return b};
 const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const title=el('div',undefined,'row');title.append(el('h3','Creator agents'),el('span','Up to 3 concurrent · 3 rounds per creator','muted'));root.append(title);
 root.append(el('p','Live dispatch requires AgntID delegation and email configuration. Shared budget is enforced by the backend.','muted'));
 const operator=input('Operator name'),evidence=input('Verified contact / action evidence');root.append(operator,evidence);
 const create=el('details');create.append(el('summary','Add creator'));const handle=input('Creator handle'),recipient=input('Allowlisted email','email');create.append(handle,recipient,button('Create agent',async()=>{if(!campaign)throw Error('Create a campaign first');await post('/negotiations/create',{revision:campaign.revision,creator_handle:handle.value,recipient:recipient.value,operator:operator.value,evidence:evidence.value});await reload()}));root.append(create);
 const lanes=(data.negotiations||[]).filter(n=>n.revision===campaign?.revision);
 const approved=[];
 for(const n of lanes){
  const card=el('article',undefined,'panel'),out=data.negotiation_outbox?.find(o=>o.negotiation_id===n.id&&o.round===n.active_round),approval=data.negotiation_approval?.find(a=>a.negotiation_id===n.id),cancelled=data.negotiation_cancellations?.some(c=>c.negotiation_id===n.id),confirmation=data.negotiation_confirmations?.find(c=>c.negotiation_id===n.id);
  card.style.marginTop='16px';card.append(el('h3',n.creator_handle||n.recipient),el('p',n.recipient+' · '+n.phase+' · Round '+n.active_round+'/'+n.max_rounds+' · '+(n.termination|| (cancelled?'Cancelled':confirmation?'Human-confirmed agreement':out?.status||'Draft')),'muted'));
  card.append(el('p','Ends '+new Date(n.deadline).toLocaleString(),'muted'));
  const currentRound=data.negotiation_rounds?.find(r=>r.negotiation_id===n.id&&r.round===n.active_round);
  const suggestion=currentRound?JSON.parse(currentRound.suggestion_json):null;
  if(suggestion)card.append(el('p','Suggested fee ₹'+(suggestion.suggested_budget_paise/100).toLocaleString('en-IN')+' · '+suggestion.rationale+' · operator approval required','muted'));
  const run=data.negotiation_runs?.filter(r=>r.negotiation_id===n.id).at(-1);if(run)card.append(el('p',run.status+' · '+(run.task_id||'No runtime task')+' · '+run.detail,'muted'));
  const action={negotiation_id:n.id,revision:campaign.revision};
  if(!out&&!cancelled&&!n.termination){
   if(n.phase==='anonymous')card.append(button('Approve brand reveal',async()=>{await post('/negotiations/reveal',{...action,operator:operator.value,evidence:evidence.value});await reload()}));
   const amount=input('Proposal fee in INR','number');amount.min='0';amount.max='50000';if(approval)amount.value=approval.amount_paise/100;else if(suggestion)amount.value=suggestion.suggested_budget_paise/100;
   const preview=el('pre',undefined,'summary');preview.style.whiteSpace='pre-wrap';let frozen;
   const approve=button('Approve exact proposal',async()=>{if(!frozen)throw Error('Preview the exact email first');await post('/negotiations/approve',{negotiation_id:n.id,amount_paise:frozen.amount_paise,preview_hash:frozen.preview_hash,operator:operator.value});await reload()});approve.disabled=true;
   amount.oninput=()=>{frozen=null;approve.disabled=true;preview.textContent=''};
   card.append(amount,button('Preview email',async()=>{frozen=await post('/negotiations/preview',{negotiation_id:n.id,amount_paise:Math.round(Number(amount.value)*100)});preview.textContent='From: '+frozen.from+'\nTo: '+frozen.recipient+'\nReply-To: '+frozen.reply_to+'\n'+frozen.subject+'\n\n'+frozen.body;approve.disabled=false}),preview,approve);
   if(approval){approved.push(n.id);card.append(el('p','Exact proposal approved · '+approval.expires_at,'muted'))}
  }
  if(!cancelled&&!n.termination)card.append(button('Cancel creator agent',async()=>{await post('/negotiations/cancel',{...action,operator:operator.value,evidence:evidence.value});await reload()}));
  if(out){
   card.append(el('p','Message-ID '+out.message_id,'muted'));
   if(['unknown','dispatching','accepted_by_smtp','accepted_reconciled'].includes(out.status)){
    card.append(button('Verify inbox receipt',async()=>{await post('/negotiations/reconcile',{operation_id:out.operation_id,outcome:'inbox_received',operator:operator.value,evidence:evidence.value});await reload()}));
    if(out.status==='unknown')card.append(button('Reconcile as not sent',async()=>{await post('/negotiations/reconcile',{operation_id:out.operation_id,outcome:'not_sent',operator:operator.value,evidence:evidence.value});await reload()}));
   }
   if(out.status==='inbox_received'&&!confirmation&&!cancelled&&!n.termination){const agreement=input('Human-approved external agreement reference');card.append(agreement,button('Record human-confirmed agreement',async()=>{await post('/negotiations/confirm',{...action,operation_id:out.operation_id,operator:operator.value,agreement_reference:agreement.value});await reload()}))}
  }
  for(const reply of data.negotiation_replies?.filter(r=>r.negotiation_id===n.id)||[]){const details=el('details');details.append(el('summary','Creator reply · '+reply.state));const body=el('pre',reply.body);body.style.whiteSpace='pre-wrap';details.append(body);if(reply.state==='quarantined')details.append(button('Verify provider receipt',async()=>{await post('/negotiations/replies/verify',{uid:reply.uid,operator:operator.value,evidence:evidence.value});await reload()}));if(reply.state==='complete'&&reply.operation_id===out?.operation_id&&out?.status==='inbox_received'&&!cancelled&&!n.termination&&n.active_round<n.max_rounds){
    const supersession=input('Evidence prior proposal was withdrawn / superseded');details.append(supersession,button('Draft next negotiation round',async()=>{await post('/negotiations/rounds/prepare',{negotiation_id:n.id,reply_uid:reply.uid,operator:operator.value,supersession_evidence:supersession.value});await reload()}));
   }
   card.append(details)}
  if(!cancelled&&!n.termination)card.append(button('Record creator decline',async()=>{await post('/negotiations/terminate',{negotiation_id:n.id,reason:'creator_declined',operator:operator.value,evidence:evidence.value});await reload()}));
  const history=data.negotiation_outbox?.filter(o=>o.negotiation_id===n.id&&o.round!==n.active_round)||[];
  if(history.length){const details=el('details');details.append(el('summary','Previous proposal rounds'));for(const old of history)details.append(el('p','Round '+old.round+' · '+old.status+' · '+old.message_id,'muted'));card.append(details)}
  root.append(card);
 }
 if(!lanes.length)root.append(el('p','No creator agents yet.','muted'));
 root.append(el('p','Reserved: ₹'+((data.reserved_paise||0)/100).toLocaleString('en-IN')+' · Unknown sends retain budget.','muted'));
 const run=button('Run approved creator agents',async()=>{if(!confirm('Dispatch the exact approved proposals through AgntID and configured email?'))return;const result=await post('/negotiations/run',{negotiation_ids:approved,operator:operator.value});await reload();toast(result.results.map(r=>r.status).join(' · '))});run.disabled=!approved.length;root.append(run);
};
