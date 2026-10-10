/* Trial-only email transport. Campaign and exact approval come from the real app;
   every sent/replied/accepted state here is a browser-side simulation. */
window.renderDemoEmail = function (state, api, reload, toast, money) {
  const root = document.getElementById('demoEmail');
  if (!root) return;
  root.closest('.section').append(root);
  root.replaceChildren();
  const campaign = state.campaign?.[0];
  const approval = state.approval?.find(a => a.revision === campaign?.revision);
  const key = 'campaign-studio-demo-mail-v1';
  let demo = {};
  try { demo = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch (_) {}
  if (demo.revision !== campaign?.revision || demo.amount !== approval?.amount_paise) demo = {revision: campaign?.revision, amount: approval?.amount_paise, stage: 0};
  const save = () => sessionStorage.setItem(key, JSON.stringify(demo));
  const el = (tag, value, cls) => { const node = document.createElement(tag); if (value !== undefined) node.textContent = value; if (cls) node.className = cls; return node; };
  const add = (...nodes) => root.append(...nodes);
  const action = (label, fn, disabled=false) => { const b=el('button',label,'primary'); b.disabled=disabled; b.onclick=async()=>{b.disabled=true;try{await fn()}catch(e){toast(e.message,true)}finally{b.disabled=false}};return b; };
  const head=el('div',undefined,'row'); head.style.justifyContent='space-between'; head.append(el('h3','Creator conversation preview'),el('span','DEMO CONVERSATION','pill')); add(head);
  add(el('p','Your brief and proposal approval are part of the working campaign. This sample conversation lets you see the creator reply, AI recommendation and partnership summary without contacting a creator.','muted'));
  if (!campaign) { add(el('p','Start a campaign first, then return to Outreach.','status')); return; }
  if (!approval) { add(el('p','Preview and approve your proposal above to continue the conversation.','status')); return; }
  const section=(title,body)=>{ const box=el('div',undefined,'panel');box.style.marginTop='16px';box.append(el('h3',title),body);add(box);return box; };
  const status=el('p',demo.stage===0?'Proposal approved · ready to preview conversation':demo.stage===1?'Proposal shared in demo · awaiting reply':demo.stage===2?'Creator reply shown · ready for AI review':demo.stage===3?'AI suggestion ready · your decision':'Partnership summary ready','status');add(status);
  const preview=el('pre','Loading approved proposal…','summary');preview.style.whiteSpace='pre-wrap';
  if (demo.stage < 2) section('Your approved proposal',preview);
  else { const details=el('details'); details.style.marginTop='16px'; details.append(el('summary','Your approved proposal'),preview); add(details); }
  api('/proposal/preview?amount_paise='+approval.amount_paise).then(p=>{
    if (p.preview_hash !== approval.payload_hash) { preview.textContent='Approved proposal has changed; preview and approve again.';return; }
    preview.textContent='From: '+p.from+'\nTo: '+p.recipient+'\nSubject: '+p.subject+'\n\n'+p.body;
  }).catch(e=>preview.textContent=e.message);
  if (demo.stage === 0) add(action('Continue to creator conversation →',async()=>{demo.stage=1;save();window.renderDemoEmail(state,api,reload,toast,money)}));
  if (demo.stage >= 1) {
    const box=section('Conversation with Maya Rao · demo',el('p','Your proposal: '+money(approval.amount_paise/100)+' for 1 Reel, 1 Story and 30 days organic reposting.','muted'));
    if (demo.stage === 1) {
      const reply=el('textarea',undefined,'field');reply.rows=4;reply.maxLength=10000;reply.value='Thanks for the offer. For this package, my rate is ₹28,000. Could you come closer to that?';reply.setAttribute('aria-label','Demo creator reply');box.append(el('label','Sample creator reply'),reply,action('Show creator reply →',async()=>{if(!reply.value.trim())throw Error('Enter a sample reply');demo.reply=reply.value.trim();demo.stage=2;save();window.renderDemoEmail(state,api,reload,toast,money)}));
    } else box.append(el('p','Creator reply (demo): '+demo.reply,'summary'));
  }
  if (demo.stage === 2) add(action('Get AI negotiation suggestion →',async()=>{const result=await api('/demo/suggest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:campaign.revision,body:demo.reply})});demo.suggestion=result;demo.stage=3;save();window.renderDemoEmail(state,api,reload,toast,money)}));
  if (demo.stage >= 3) {
    const result=demo.suggestion;
    const box=section('AI negotiation suggestion',el('p','Suggested fee: '+money(result.suggested_budget_paise/100),'status'));
    box.append(el('p','Why: '+result.rationale,'muted'),el('p','Draft opening: '+result.counteroffer_intro,'muted'),el('p','Risk flags: '+(result.risk_flags.length?result.risk_flags.join(' · '):'None returned'),'muted'),el('p','Review only. This suggestion is not an approved or sent counteroffer.','muted'));
    if (demo.stage === 3) {
      const operator=el('input',undefined,'field');operator.placeholder='Operator name for simulated final record';operator.maxLength=120;
      const fee=el('input',undefined,'field');fee.type='number';fee.min='0';fee.max=String(Math.min(campaign.budget_paise,2500000)/100);fee.value=String(Math.min(result.suggested_budget_paise,campaign.budget_paise,2500000)/100);fee.setAttribute('aria-label','Human-confirmed illustrative fee in INR');
      box.append(el('label','Proposed partnership fee in INR'),fee,operator,action('View partnership summary →',async()=>{const paise=Math.round(Number(fee.value)*100);if(!operator.value.trim())throw Error('Enter the presenter or operator name');if(!Number.isInteger(paise)||paise<0||paise>Math.min(campaign.budget_paise,2500000))throw Error('Fee must fit the campaign budget and ₹25,000 proposal cap');demo.operator=operator.value.trim();demo.finalPaise=paise;demo.stage=4;save();window.renderDemoEmail(state,api,reload,toast,money)}));
    }
  }
  if (demo.stage === 4) {
    const box=section('Partnership summary · demo',el('p','This is how the completed partnership would be presented after human confirmation.','status'));
    box.append(el('p','Creator: Maya Rao (demo) · Package: 1 Reel + 1 Story + 30 days organic reposting · Illustrative agreed fee: '+money(demo.finalPaise/100),'summary'),el('p','Simulated by '+demo.operator+'. No contract, payment or publishing action occurred.','muted'));
    root.insertBefore(box, root.querySelector('details'));
  }
  if (demo.stage > 0) {const reset=action('Restart conversation preview',async()=>{demo={revision:campaign.revision,amount:approval.amount_paise,stage:0};save();window.renderDemoEmail(state,api,reload,toast,money)});reset.className='quiet';add(reset)}
};
