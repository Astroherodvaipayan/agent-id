const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const page=fs.readFileSync('app/web/index.html','utf8');
const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,style:{},classList:{add(){},toggle(){}},append(){},replaceChildren(){}});return elements.get(id)};
let approval=[],sent;
const campaign={idea:'Test campaign',target_markets:'["India"]',revision:1,budget_paise:4000000,brief:'Brief',evidence:'Test'};
const context={document:{body:{classList:{toggle(){}}},getElementById:get,querySelectorAll:()=>[],createElement:()=>({append(){},setAttribute(){},classList:{toggle(){}},style:{}})},history:{replaceState(){}},location:{hash:''},window:{},setTimeout:()=>0,clearTimeout(){},confirm:()=>true,crypto:{randomUUID:()=> 'isolated-ui-test'},fetch:async(path,opts={})=>{
 let data={};
 if(path==='/state')data={campaign:[campaign],approval,guardrail_review:[{status:'approved',findings_json:'[]'}],readiness:{outbound_ready:true},outbox:[],inbound:[]};
 else if(path==='/workspace/config')data={controlled_creator_email:'creator@example.test'};
 else if(path.startsWith('/proposal/preview'))data={preview_hash:'test-hash',recipient:'creator@example.test',subject:'Test',body:'Nonbinding'};
 else if(path==='/approve'){approval=[{...JSON.parse(opts.body)}]}
 else if(path==='/send'){sent=JSON.parse(opts.body);data={status:'isolated_no_send'}}
 return {ok:true,json:async()=>data};
}};
vm.createContext(context);vm.runInContext(page.split('<script>')[1].split('</script>')[0],context);
(async()=>{
 await vm.runInContext('load()',context);assert.equal(get('offer').value,40000);
 get('offer').value='24000';get('offer').oninput();await vm.runInContext('load()',context);assert.equal(get('offer').value,'24000');
 await get('previewBtn').onclick();get('approver').value='Test';await get('approveBtn').onclick();assert.equal(get('offer').value,24000);
 await vm.runInContext('load()',context);assert.equal(get('offer').value,24000);
 await get('sendBtn').onclick();assert.equal(sent.amount_paise,2400000);
 console.log('Approved 24k survives refresh; mocked send uses 24k. No network or SMTP.');
})().catch(e=>{console.error(e);process.exitCode=1});
