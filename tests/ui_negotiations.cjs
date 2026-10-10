const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element{constructor(tag){this.tag=tag;this.children=[];this.style={};this.value='';this.textContent=''}append(...items){this.children.push(...items)}replaceChildren(){this.children=[]}}
const root=new Element('root'),calls=[];
const context={window:{},document:{getElementById:()=>root,createElement:tag=>new Element(tag)},confirm:()=>true};vm.createContext(context);vm.runInContext(fs.readFileSync('app/web/negotiations.js','utf8'),context);
const lane={id:'creator-a',revision:1,active_round:2,max_rounds:3,deadline:'2026-10-10T20:00:00Z',recipient:'a@example.test',phase:'revealed'};
const state={campaign:[{revision:1}],negotiation:{negotiations:[lane],negotiation_rounds:[{negotiation_id:lane.id,round:2,suggestion_json:JSON.stringify({suggested_budget_paise:800000,rationale:'Mock'})}],negotiation_outbox:[{negotiation_id:lane.id,round:1,status:'inbox_received',message_id:'<old>'}]}};
const all=e=>[e,...e.children.flatMap(all)];
context.window.renderCreatorLanes(state,async(path,opts)=>{calls.push([path,JSON.parse(opts.body)]);return {amount_paise:800000,preview_hash:'hash',from:'brand@test',recipient:lane.recipient,reply_to:'brand@test',body:'Nonbinding',subject:'Proposal'}},async()=>{},()=>{});
const elements=all(root),preview=elements.find(e=>e.textContent==='Preview email'),approve=elements.find(e=>e.textContent==='Approve exact proposal');
assert(preview&&approve.disabled);
assert(elements.some(e=>e.textContent==='Previous proposal rounds'));
const fee=elements.find(e=>e.type==='number');assert.equal(fee.value,8000);
(async()=>{await preview.onclick();assert(!approve.disabled);fee.value='9000';fee.oninput();assert(approve.disabled);assert.equal(calls[0][1].negotiation_id,lane.id);assert.equal(calls[0][1].amount_paise,800000);console.log('Revised-round UI uses current lane, preserves history and invalidates edited previews. No network.');})().catch(e=>{console.error(e);process.exitCode=1});
