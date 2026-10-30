'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require(path.resolve(__dirname,'../../node_modules/jsdom'));
const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),script=fs.readFileSync(path.join(__dirname,'qc-workflow.js'),'utf8'),schedule=fs.readFileSync(path.join(__dirname,'qc-schedule.js'),'utf8');
const copy=x=>JSON.parse(JSON.stringify(x));
const tick=()=>new Promise(r=>setTimeout(r,5));
const source={id:'order-1',factory:'huaxing',sourceRevision:1,sourceVersion:1,customer:'客户 <A>',poNo:'0000123',customerPo:'00991',productNo:'00101',productName:'测试产品',quantity:'100',dateFrom:'2026-10-26',dateTo:'2026-10-26',shipDate:'2026-10-30',shippedQuantity:'0',sourceStatus:'active',agency:'行验',tasks:[]};
function task(state='waiting'){return {id:'task-1',sourceId:source.id,source:copy(source),factory:'huaxing',method:'internal',batch:'首验',state,revision:1,plannedDate:'2026-10-26',plannedQuantity:'100',attachments:[],history:[],execution:{actualDate:'',actualQuantity:null,sampleQuantity:null,inspector:'',institution:'',reportNo:'',reportMissingReason:'',result:'',remark:'',defects:[],measurements:[],resultExplanation:''}};}
async function page({items=[],review=false,failSave=false,native=false,failUpload=false,legacyRecords=[],sources=[source]}={}){
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/api/qc-department/huaxing/u-test/'}),w=dom.window,calls=[];let rows=copy(items);
 w.__QC_NEXUS={factory:'huaxing',user:{name:'测试 QC'},exportAllowed:true,workflow:{create:true,edit:true,review,export:true,manual:true}};
 if(native){
  const add=w.document.addEventListener.bind(w.document);w.document.addEventListener=(name,...args)=>{if(name!=='DOMContentLoaded')add(name,...args);};
  w.eval(fs.readFileSync(path.join(__dirname,'app.js'),'utf8')+'\nstate='+JSON.stringify({records:legacyRecords,nextId:31})+';currentPage="records";');
  w.document.addEventListener=add;
  w.can=()=>true;w.renderSupplierDatalist=()=>{};w.renderCustomerDatalist=()=>{};w.renderInspectorDatalist=()=>{};w.renderProcessTypeDatalist=()=>{};w.bindNameWhitelistCheck=()=>{};w.getSupplierOptions=()=>['名发'];w.getCustomerOptions=()=>['ZURU'];w.getProcessTypeOptions=()=>[];
 }
w.realShowPage=w.showPage;w.showToast=()=>{};w.confirm=()=>true;w.prompt=()=> '需补充说明';w.showPage=name=>w.QcWorkflow.onPage(name);
 w.fetch=async(url,opts={})=>{
  const body=opts.body?JSON.parse(opts.body):undefined;calls.push({url,body});let data;
  if(url==='api/schedule-source')data={contract_version:'2',factory_id:'huaxing',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:copy(sources)};
  else if(url==='api/workflow/tasks'&&!body)data={items:copy(rows)};
  else if(url==='api/workflow/projections')data={items:[]};
  else if(url==='api/workflow/tasks'&&body){const t=task();rows=[t];data={items:[copy(t)]};}
  else if(url==='api/workflow/legacy'){const t=task('draft');t.source.kind='legacy';t.legacyId=body.recordId;rows=[t];data=copy(t);}
  else if(url==='api/workflow/manual'){const t=task('draft');t.source.kind='manual';t.method=body.method;t.execution=copy(body.execution);rows=[t];data=copy(t);}
  else if(url==='api/workflow/tasks/task-1/attach'){if(failUpload)return {ok:false,status:503,json:async()=>({detail:'照片上传失败'})};rows[0].attachments.push({id:'photo-'+rows[0].attachments.length,name:body.name,mime:'image/png',size:12,caption:body.caption,actor:'QC'});rows[0].revision++;data=copy(rows[0]);}
  else if(url==='api/workflow/tasks/task-1'&&!body)data=copy(rows[0]);
  else if(url==='api/workflow/tasks/task-1/save'){
   if(failSave)return {ok:false,status:409,json:async()=>({detail:'记录已变化'})};
   rows[0].execution=copy(body.execution);rows[0].state='draft';rows[0].revision++;data=copy(rows[0]);
  }else if(url==='api/workflow/tasks/task-1/submit'){rows[0].state='pending';rows[0].revision++;data=copy(rows[0]);}
  else if(url==='api/workflow/tasks/task-1/return'){rows[0].state='returned';rows[0].revision++;rows[0].reviewReason=body.reason;data=copy(rows[0]);}
  else if(url==='api/workflow/tasks/task-1/approve'){rows[0].state='approved';rows[0].revision++;data=copy(rows[0]);}
  else throw Error('unexpected '+url);
  return {ok:true,json:async()=>data};
 };
 w.eval(schedule);w.eval(script);await tick();await w.QcWorkflow.load();return {dom,w,d:w.document,calls,get rows(){return rows;}};
}
test('formal schedule selection directly pushes only checked sources without a confirmation dialog',async()=>{
 const p=await page();try{
  await p.w.renderSalesSchedule();const input=p.d.querySelector('[data-pick]');assert.ok(input);input.click();
  assert.equal(p.d.getElementById('qsPush').disabled,false);p.d.getElementById('qsPush').click();
  assert.equal(p.d.querySelector('.qwf-dialog'),null);await settled(p);
  const call=p.calls.find(c=>c.url==='api/workflow/tasks'&&c.body);assert.equal(call.body.items.length,1);assert.equal(call.body.items[0].sourceId,'order-1');assert.equal(call.body.items[0].sourceRevision,1);
  assert.equal(p.rows[0].execution.result,'');assert.equal(p.w.QcWorkflow.model.items[0].state,'waiting');
 }finally{p.dom.window.close();}
});
test('draft editing and submit lock are distinct; no approval buttons in inspector workbench',async()=>{
 const p=await page({items:[task()]});try{
  await p.w.QcWorkflow.openTask('task-1','records');assert.equal(p.d.querySelector('[data-execution="result"]').value,'');
  for(const [key,value] of Object.entries({actualDate:'2026-10-26',actualQuantity:'100',sampleQuantity:'10',inspector:'张 QC',result:'REJ',remark:'划痕 <script>'})){const el=p.d.querySelector('[data-execution="'+key+'"]');el.value=value;el.dispatchEvent(new p.w.Event('input',{bubbles:true}));}
  p.d.querySelector('[data-save]').click();await tick();await tick();assert.equal(p.rows[0].state,'draft');assert.equal(p.rows[0].execution.result,'REJ');
  assert.equal(p.calls.filter(c=>c.url.endsWith('/submit')).length,0);
  p.d.querySelector('[data-submit]').click();await tick();await tick();assert.equal(p.rows[0].state,'pending');
  assert.equal(p.d.querySelector('[data-save]'),null);assert.equal(p.d.querySelector('[data-execution="result"]').disabled,true);assert.equal(p.d.querySelector('[data-upload]'),null);assert.equal(p.d.querySelector('[data-review]'),null);
  assert.equal(p.d.querySelector('.qwf-dialog script'),null);
 }finally{p.dom.window.close();}
});
test('supervisor reviews full fields, returns with reason, QC can edit again',async()=>{
 const t=task('pending');t.execution={...t.execution,actualDate:'2026-10-26',actualQuantity:'100',result:'PASS',inspector:'QC',remark:'核对原报告'};t.method='external';t.attachments=[{id:'photo',name:'问题照片.png',mime:'image/png',size:100,caption:'外壳划痕',actor:'QC'}];
 const p=await page({items:[t],review:true});try{
  await p.w.QcWorkflow.openTask('task-1','review');assert.match(p.d.querySelector('.qwf-dialog').textContent,/核对原报告/);assert.ok(p.d.querySelector('img[alt="外壳划痕"]'));
  assert.ok(p.d.querySelector('[data-review="approve"]'));assert.equal(p.d.querySelector('[data-save]'),null);
  p.d.querySelector('[data-review="return"]').click();await tick();await tick();assert.equal(p.rows[0].state,'returned');
  await p.w.QcWorkflow.openTask('task-1','records');assert.ok(p.d.querySelector('[data-save]'));assert.equal(p.d.querySelector('[data-execution="result"]').value,'PASS');
 }finally{p.dom.window.close();}
});
test('conflict keeps the typed draft visible and gives a recovery message',async()=>{
 const p=await page({items:[task()],failSave:true});try{
  await p.w.QcWorkflow.openTask('task-1','records');const remark=p.d.querySelector('[data-execution="remark"]');remark.value='还没保存的现场情况';remark.dispatchEvent(new p.w.Event('input',{bubbles:true}));
  p.d.querySelector('[data-save]').click();await tick();assert.equal(remark.value,'还没保存的现场情况');assert.match(p.d.querySelector('[data-error]').textContent,/记录已变化/);assert.equal(p.w.QcWorkflow.model.dirty,true);
 }finally{p.dom.window.close();}
});
test('measurement FAIL warns but never rewrites an external report PASS',async()=>{
 const p=await page({items:[task()]});try{
  await p.w.QcWorkflow.openTask('task-1','records');p.d.querySelector('[data-execution="result"]').value='PASS';
  p.d.querySelector('[data-add-row="measurements"]').click();p.d.querySelector('[data-cell="result"]').value='FAIL';p.d.querySelector('[data-cell="result"]').dispatchEvent(new p.w.Event('change',{bubbles:true}));
  assert.equal(p.d.querySelector('[data-execution="result"]').value,'PASS');assert.match(p.d.querySelector('[data-calculation]').textContent,/测量含 FAIL/);
 }finally{p.dom.window.close();}
});
test('records and review use original layout while the schedule controls remain',async()=>{
 const p=await page();try{
  assert.equal(p.d.getElementById('recordsTableWrap').closest('details.qwf-legacy'),null);assert.equal(p.d.getElementById('reviewTableWrap').closest('details.qwf-legacy'),null);
  assert.equal(p.d.getElementById('qwf-records'),null);assert.equal(p.d.getElementById('qwf-review'),null);assert.ok(p.d.getElementById('qsPush'));assert.ok(p.d.getElementById('qsSelectAll'));
  assert.equal(p.d.querySelectorAll('.qs-table thead tr:last-child th').length,14);assert.ok(p.d.getElementById('btnExportInspectionExcel'));assert.ok(p.d.getElementById('page-daily'));
 }finally{p.dom.window.close();}
});

test('failed photo upload blocks submission and keeps selection',async()=>{
 const p=await page({items:[task()],failUpload:true});try{
  await p.w.QcWorkflow.openTask('task-1','records');const input=p.d.querySelector('[data-files]');
  Object.defineProperty(input,'files',{value:[new p.w.File(['image'],'未上传.png',{type:'image/png'})]});input.dispatchEvent(new p.w.Event('change',{bubbles:true}));
  p.d.querySelector('[data-submit]').click();await tick();assert.match(p.d.querySelector('[data-error]').textContent,/照片上传失败/);assert.equal(input.files.length,1);
  assert.equal(p.calls.filter(c=>c.url.endsWith('/submit')).length,0);assert.equal(p.w.QcWorkflow.model.dirty,true);
 }finally{p.dom.window.close();}
});
test('review workspace remains read-only even for a returned record',async()=>{
 const p=await page({items:[task('returned')],review:true});try{
  await p.w.QcWorkflow.openTask('task-1','review');assert.equal(p.d.querySelector('[data-save]'),null);assert.equal(p.d.querySelector('[data-submit]'),null);
 }finally{p.dom.window.close();}
});

test('direct push rejects concurrent clicks and reuses an uncertain request on retry',async()=>{
 const p=await page();try{
  const original=p.w.fetch;let release;
  p.w.fetch=async(url,opts)=>url==='api/workflow/tasks'&&opts?.body?await new Promise(resolve=>{release=()=>resolve({ok:false,status:503,json:async()=>({detail:'暂时不可用'})});}):original(url,opts);
  const pending=p.w.QcWorkflow.preparePush([source]);await p.w.QcWorkflow.preparePush([source]);assert.equal(p.w.QcWorkflow.model.busy,true);release();await pending;
  const sent=p.w.QcWorkflow.model.directPush.payload;assert.ok(sent);assert.equal(p.d.querySelector('.qwf-dialog'),null);
  p.w.fetch=original;await p.w.QcWorkflow.preparePush([source]);
  assert.deepEqual(p.calls.find(c=>c.url==='api/workflow/tasks'&&c.body).body,JSON.parse(JSON.stringify(sent)));assert.equal(p.w.QcWorkflow.model.directPush,null);
  p.w.fetch=async(url,opts)=>url==='api/workflow/tasks'&&opts?.body?{ok:false,status:409,json:async()=>({detail:'订单已变化'})}:original(url,opts);
  await p.w.QcWorkflow.preparePush([source]);assert.equal(p.w.QcWorkflow.model.directPush,null);assert.equal(p.w.QcWorkflow.model.busy,false);
 }finally{p.dom.window.close();}
});


async function settled(p){for(let i=0;i<80&&p.w.QcWorkflow.model.busy;i++)await tick();assert.equal(p.w.QcWorkflow.model.busy,false);}
test('native form keeps all original fields and historical multi-axis data when only notes change',async()=>{
 const t=task('returned');t.source.kind='legacy';t.legacyId=22;
 const original={date:'日期待核对',inspDate:'2026-10-26',supplier:'名发',client:'ZURU',processType:'印刷',productNo:'00123',productName:'粉色熊',deliveryNo:'0005501',orderNo:'NA',type:'半成品',qty:600,sampleQty:80,pass:72,fail:8,defectRate:'10.00%',defect:'大小脚，斜眼',result:'PASS',qc:'QC',remark:'原备注',aqlLevel:'MAJ 0.65',defects:[],measurements:[{item:'纸箱',measureType:'lwh',standardL:'10',standardW:'20',standardH:'30',toleranceL:'1',lValues:['11'],wValues:['20'],hValues:['30'],values:[],result:'FAIL'}]};
 t.execution={...t.execution,record:copy(original),actualDate:original.inspDate,actualQuantity:'600',sampleQuantity:'80',inspector:'QC',result:'PASS',remark:'原备注'};
 const p=await page({items:[t],native:true});try{
  await p.w.QcWorkflow.openTask(t.id,'records');
  for(const key of ['date','inspDate','supplier','client','processType','productNo','productName','deliveryNo','orderNo','type','qty','sampleQty','pass','fail','defectRate','qc','result','remark'])assert.ok(p.d.querySelector('.qwf-dialog #f_'+key),key);
  assert.equal(p.d.getElementById('f_result').value,'PASS');p.w._syncFormResult();assert.equal(p.d.getElementById('f_result').value,'PASS');
  const note=p.d.getElementById('f_remark');note.value='补充备注';note.dispatchEvent(new p.w.Event('input',{bubbles:true}));
  p.d.querySelector('[data-save]').click();await settled(p);
  assert.deepEqual(p.rows[0].execution.record.measurements,original.measurements);
  for(const key of ['date','pass','fail','defectRate','defect','deliveryNo','aqlLevel'])assert.deepEqual(p.rows[0].execution.record[key],original[key],key);
  assert.equal(p.rows[0].execution.remark,'补充备注');assert.equal(p.rows[0].execution.result,'PASS');
  p.w.QcWorkflow.close();assert.ok(p.d.querySelector('#modalOverlay #panelSingle'));assert.equal(p.d.querySelectorAll('#f_result').length,1);
 }finally{p.dom.window.close();}
});
test('native new record saves draft without conclusion, submits manual result, supervisor return unlocks',async()=>{
 const p=await page({native:true,review:true});try{
  await p.w.QcWorkflow.openNew();assert.equal(p.d.getElementById('f_result').value,'');
  assert.ok(p.d.querySelector('.qwf-dialog #panelBatch'));assert.ok(p.d.querySelector('.qwf-dialog #tabBatch'));
  p.d.getElementById('f_supplier').value='名发';p.d.getElementById('f_client').value='ZURU';p.d.getElementById('f_productNo').value='00123';
  p.d.querySelector('[data-save]').click();await settled(p);assert.equal(p.rows[0].execution.result,'');assert.equal(p.rows[0].state,'draft');
  for(const [key,value] of Object.entries({inspDate:'2026-10-26',qty:'100',sampleQty:'10',qc:'张 QC',result:'REJ',remark:'照片见附件'})){const node=p.d.getElementById('f_'+key);node.value=value;node.dispatchEvent(new p.w.Event('input',{bubbles:true}));}
  p.d.querySelector('[data-submit]').click();await settled(p);assert.equal(p.rows[0].state,'pending');assert.equal(p.d.getElementById('f_result').disabled,true);assert.equal(p.d.querySelector('[data-save]'),null);
  await p.w.QcWorkflow.openTask('task-1','review');assert.equal(p.d.getElementById('f_remark').value,'照片见附件');
  p.d.querySelector('[data-review="return"]').click();await settled(p);
  await p.w.QcWorkflow.openTask('task-1','records');assert.equal(p.d.getElementById('f_result').disabled,false);assert.equal(p.d.getElementById('f_result').value,'REJ');
  assert.equal(p.d.querySelectorAll('#f_result').length,1);
 }finally{p.dom.window.close();}
});
test('workflow rows appear inside original table and review tabs, keeping checkboxes for batch only',async()=>{
 const t=task('pending');t.execution.result='PASS';const p=await page({items:[t],native:true});try{
  p.w.filterRecords();assert.ok(p.d.querySelector('#recordsTable [data-workflow="task-1"]'));assert.equal(p.d.querySelectorAll('#recordsTable thead th').length,20);
  assert.equal(p.d.querySelector('[data-workflow] input[type=checkbox]'),null);
  p.w.renderReviewPage();assert.ok(p.d.querySelector('#reviewTableWrap [data-workflow="task-1"]'));
 }finally{p.dom.window.close();}
});

test('native OCR queue advances only after successful draft persistence and closes cleanly',async()=>{
 const p=await page({native:true});try{
  p.w.eval(fs.readFileSync(path.join(__dirname,'ai-ocr.js'),'utf8'));
  await p.w.QcWorkflow.openNew();
  p.w.__qcQueue={idx:0,common:{date:'2026-10-25',inspDate:'2026-10-26',supplier:'名发',deliveryNo:'0001',orderNo:'NA',type:'成品'},items:[{productNo:'001',qty:100},{productNo:'002',productName:'第二件',qty:200}]};
  p.d.getElementById('f_productNo').value='001';
  p.d.querySelector('[data-save]').click();await settled(p);await tick();
  assert.equal(p.w.__qcQueue.idx,1);assert.equal(p.d.getElementById('f_productNo').value,'002');assert.equal(p.d.getElementById('f_qty').value,'200');assert.equal(p.d.getElementById('f_result').value,'');
  assert.equal(p.w.QcWorkflow.model.task.id,null);
  p.w.QcWorkflow.close();assert.equal(p.w.__qcQueue,null);
 }finally{p.dom.window.close();}
});
test('native OCR queue does not advance when a saved draft conflicts',async()=>{
 const t=task('draft');t.source.kind='manual';const p=await page({native:true,items:[t],failSave:true});try{
  p.w.eval(fs.readFileSync(path.join(__dirname,'ai-ocr.js'),'utf8'));
  await p.w.QcWorkflow.openTask(t.id,'records');p.w.__qcQueue={idx:0,common:{},items:[{},{}]};
  p.d.querySelector('[data-save]').click();await settled(p);await tick();
  assert.equal(p.w.__qcQueue.idx,0);assert.match(p.d.querySelector('[data-error]').textContent,/记录已变化/);
 }finally{p.dom.window.close();}
});

test('factory switch protection sees native notes, unuploaded photos and in-flight direct push',async()=>{
 const p=await page({items:[task()],native:true});try{
  await p.w.QcWorkflow.openTask('task-1','records');assert.equal(p.w.QcWorkflow.navigationState().dirty,false);
  const remark=p.d.getElementById('f_remark');remark.value='未保存的现场备注';remark.dispatchEvent(new p.w.Event('input',{bubbles:true}));
  assert.equal(p.w.QcWorkflow.navigationState().dirty,true);
  p.w.QcWorkflow.model.dirty=false;
  Object.defineProperty(p.d.querySelector('[data-camera]'),'files',{value:[new p.w.File(['image'],'现场.png')]});
  assert.equal(p.w.QcWorkflow.navigationState().dirty,true);
  p.w.QcWorkflow.model.busy=true;assert.equal(p.w.QcWorkflow.navigationState().busy,true);p.w.QcWorkflow.model.busy=false;
  p.w.QcWorkflow.close();const pending=p.w.QcWorkflow.preparePush([source]);
  assert.equal(p.w.QcWorkflow.navigationState().busy,true);assert.equal(p.d.querySelector('[data-plan-batch]'),null);await pending;
 }finally{p.dom.window.close();}
});


test('inspector uses account interface, is read-only, and ignores DOM tampering',async()=>{
 for(const native of [true,false]){
  const p=await page({items:[task()],native});try{
   p.w.__QC_NEXUS.inspector={id:'account-2',name:'登录检验员'};
   await p.w.QcWorkflow.openTask('task-1','records');
   const field=p.d.querySelector(native?'#f_qc':'[data-execution="inspector"]');
   assert.equal(field.value,'登录检验员');assert.ok(field.readOnly||field.disabled);
   field.value='冒名者';p.d.querySelector('[data-save]').click();await tick();await tick();
   const call=p.calls.find(c=>c.url.endsWith('/save'));
   assert.equal(call.body.execution.inspector,'登录检验员');
   if(native)assert.equal(call.body.execution.record.qc,'登录检验员');
  }finally{p.dom.window.close();}
 }
});
test('viewing submitted record preserves original inspector without writes',async()=>{
 const t=task('pending');t.execution.inspector='原检验员';
 const p=await page({items:[t],native:true});try{
  await p.w.QcWorkflow.openTask('task-1','records');
  assert.equal(p.d.querySelector('#f_qc').value,'原检验员');
  assert.equal(p.calls.filter(c=>c.body).length,0);
 }finally{p.dom.window.close();}
});


test('legacy row opens locked records read-only and only granted test rows for filling',async()=>{
 const p=await page({native:true});try{
  const r={id:31,status:null,qc:'',client:'Dickie',productNo:'001',qty:100,remark:'测试'};
  await p.w.QcWorkflow.openRecord(r);
  assert.ok(p.d.querySelector('.qwf-dialog'));
  assert.equal(p.d.querySelector('[data-save]'),null);
  assert.equal(p.d.querySelector('#f_qty').disabled,true);
  assert.equal(p.calls.filter(c=>c.body).length,0);
  p.w.QcWorkflow.close();p.w.__QC_TEST_ENTRY_IDS=new Set([31]);
  await p.w.QcWorkflow.openRecord(r);
  assert.ok(p.d.querySelector('[data-save]'));
  assert.equal(p.d.querySelector('#f_qty').disabled,false);
  assert.equal(p.d.querySelector('#f_qc').readOnly,true);
  assert.equal(p.calls.filter(c=>c.url==='api/workflow/legacy').length,1);
 }finally{p.dom.window.close();}
});
test('row selection opens its drawer; embedded controls do not activate rows',async()=>{
 const p=await page({native:true,items:[task()],legacyRecords:[{id:31,productName:'货品 A'},{id:32,productName:'货品 B'}]});try{
  let opened=0;p.w.QcWorkflow.openRecord=()=>opened++;
  const td=p.d.createElement('td'),button=p.d.createElement('button'),checkbox=p.d.createElement('input');
  assert.equal(p.d.querySelector('#inspectionSelection').textContent,'未选中记录');
  for(const target of [button,checkbox])p.w.openRecordRow({target},31);
  assert.equal(p.d.querySelector('#inspectionSelection').textContent,'未选中记录');
  const before=p.calls.length;
  p.w.openRecordRow({target:td},31);
  assert.equal(opened,1);assert.equal(p.calls.length,before);
  assert.equal(p.d.querySelectorAll('.inspection-active').length,1);
  assert.match(p.d.querySelector('#inspectionSelection').textContent,/货品 A/);
  p.w.openRecordRow({target:td},32);
  assert.equal(p.d.querySelectorAll('.inspection-active').length,1);
  assert.match(p.d.querySelector('#inspectionSelection').textContent,/货品 B/);
  p.w.filterRecords();assert.equal(p.d.querySelectorAll('.inspection-active').length,1);
  p.w.startSelectedInspection();assert.equal(opened,3);
  await p.w.QcWorkflow.openRow({target:td},'task-1');
  await tick();assert.ok(p.d.querySelector('.qwf-drawer'));
  await p.w.startSelectedInspection();assert.ok(p.d.querySelector('.qwf-dialog'));
 }finally{p.dom.window.close();}
});
test('filtering selected row clears context; keyboard selection opens drawer',async()=>{
 const p=await page({native:true,legacyRecords:[{id:31,productName:'目标货品'}]});try{
  const row=p.d.querySelector('#recordsTable tr[data-id="31"]');let prevented=false;
  p.w.selectInspectionWithKey({target:row,currentTarget:row,key:'Enter',preventDefault(){prevented=true;}},'legacy:31');
  assert.equal(prevented,true);assert.equal(p.d.querySelectorAll('.inspection-active').length,1);
  assert.ok(p.d.querySelector('.qwf-drawer'));
  p.d.querySelector('#searchInput').value='完全不匹配';p.w.filterRecords();
  assert.equal(p.d.querySelector('#inspectionSelection').textContent,'未选中记录');
  assert.equal(p.d.querySelector('#inspectionSelection').textContent,'未选中记录');
 }finally{p.dom.window.close();}
});



test('linked test draft keeps original twenty-column legacy row renderer',async()=>{
 const t=task('draft');t.legacyId=31;t.testEntry=true;t.reference=true;t.source.kind='legacy';
 const p=await page({native:true,items:[t]});try{
  p.w.filterRecords();
  const row=p.d.querySelector('#recordsTable tbody tr');
  assert.equal(row.children.length,20);assert.equal(row.dataset.id,'31');
  assert.equal(row.classList.contains('qwf-record'),false);
  assert.ok(row.querySelector('input.row-check'));
  assert.equal(row.children[1].textContent.trim(),'31');
  assert.equal(row.querySelector('.qwf-status'),null);
  assert.match(row.children[2].getAttribute('style'),/white-space:nowrap/);
 }finally{p.dom.window.close();}
});


test('linked test row escapes display values and cannot be selected through select-all',async()=>{
 const t=task('draft');t.legacyId=31;t.testEntry=true;t.source.kind='legacy';
 const text='<img src=x onerror="alert(1)">';
 t.execution.record={supplier:text,productName:text,defect:text};
 const p=await page({native:true,items:[t]});try{
  p.w.filterRecords();const row=p.d.querySelector('#recordsTable tbody tr');
  assert.equal(row.querySelector('img'),null);assert.equal(row.querySelector('[onerror]'),null);
  assert.equal(row.children[4].textContent,text);assert.equal(row.children[4].getAttribute('title'),text);
  assert.equal(p.w.QcWorkflow.model.items[0].execution.record.supplier,text);
  p.w._onCheckAll({checked:true});
  assert.equal(row.querySelector('.row-check').checked,false);
  assert.equal(row.classList.contains('row-selected'),false);
 }finally{p.dom.window.close();}
});


test('reopening drawer keeps inspector bound and native fields intact',async()=>{
 const p=await page({native:true,items:[task('draft')]});try{
  await p.w.QcWorkflow.openTask('task-1','records');
  const position=()=>[...p.d.querySelector('#f_qc').parentElement.parentElement.children].indexOf(p.d.querySelector('#f_qc').parentElement);
  const before=position();p.w.QcWorkflow.close();
  await p.w.QcWorkflow.openTask('task-1','records');assert.equal(position(),before);
  const group=p.d.querySelector('#f_qc').parentElement;
  assert.equal(group.closest('.qwf-source-controls').hidden,true);
  assert.equal(p.d.querySelectorAll('#f_qc').length,1);assert.equal(p.d.querySelector('#f_qc').readOnly,true);
 }finally{p.dom.window.close();}
});


test('drawer is nonmodal, collapse/resume retains typed fields and selected files',async()=>{
 const t=task('draft');const p=await page({native:true,items:[t]});try{
  await p.w.QcWorkflow.openTask(t.id,'records');const drawer=p.d.querySelector('.qwf-drawer');
  assert.equal(drawer.getAttribute('aria-modal'),'false');
  const qty=p.d.querySelector('#f_qty');qty.value='73';qty.dispatchEvent(new p.w.Event('input',{bubbles:true}));
  const file=p.d.querySelector('[data-files]'),photo=new p.w.File(['test'],'photo.png',{type:'image/png'});Object.defineProperty(file,'files',{value:[photo]});
  p.d.querySelector('[data-collapse]').click();assert.equal(drawer.hasAttribute('open'),false);
  assert.equal(p.w.QcWorkflow.navigationState().dirty,true);
  await p.w.QcWorkflow.openTask(t.id,'records');assert.equal(p.d.querySelector('.qwf-drawer'),drawer);assert.equal(qty.value,'73');assert.equal(file.files[0],photo);
  assert.equal(p.calls.filter(c=>c.url==='api/workflow/tasks/task-1').length,1);
 }finally{p.dom.window.close();}
});
test('cancelled selection keeps original highlighted record and unsaved form',async()=>{
 const p=await page({native:true,legacyRecords:[{id:31,productName:'A'},{id:32,productName:'B'}]});try{
  await p.w.selectInspectionRecord('legacy:31');const drawer=p.d.querySelector('.qwf-drawer');p.w.QcWorkflow.model.dirty=true;p.w.confirm=()=>false;
  await p.w.selectInspectionRecord('legacy:32');assert.equal(p.d.querySelector('.inspection-active').dataset.id,'31');assert.equal(p.d.querySelector('.qwf-drawer'),drawer);
 }finally{p.dom.window.close();}
});
test('test plan quantity remains reference, missing facts remain blank and original preserved',async()=>{
 const t=task('draft');t.testEntry=true;t.source.kind='legacy';t.legacyId=31;t.legacyOriginal={qty:300,type:''};t.execution.actualQuantity=300;t.execution.record={qty:300,type:'',supplier:'',date:'',deliveryNo:''};
 const before=copy(t);const p=await page({native:true,items:[t]});try{
  await p.w.QcWorkflow.openTask(t.id,'records');assert.equal(p.d.querySelector('#f_qty').value,'');assert.match(p.d.querySelector('.qwf-carried').textContent,/排期数量（参考）300/);
  assert.equal(p.d.querySelector('#f_type').value,'');assert.equal(p.d.querySelector('#f_supplier').value,'');assert.equal(p.d.querySelector('#f_date').value,'');assert.equal(p.d.querySelector('[data-submit]').disabled,true);
  assert.ok(p.d.querySelector('#f_supplier').closest('.qwf-business-edit'));assert.deepEqual(p.rows[0],before);
  p.d.querySelector('#f_supplier').value='业务核对供应商';p.d.querySelector('#f_qty').value='75';
  assert.equal(p.w.QcWorkflow.readForm().record.supplier,'业务核对供应商');assert.equal(p.w.QcWorkflow.readForm().actualQuantity,75);
  assert.equal(p.w.QcWorkflow.readForm().inspector,'测试 QC');
  p.w.QcWorkflow.close();await p.w.QcWorkflow.openTask(t.id,'review');assert.equal(p.d.querySelector('.qwf-drawer'),null);assert.equal(p.d.querySelector('#f_qty').value,'300');
 }finally{p.dom.window.close();}
});
test('saved test actual quantity survives reopening; source summary escapes markup',async()=>{
 const t=task('draft');t.testEntry=true;t.history=[{action:'save',snapshot:{attachments:[]}}];t.execution.actualQuantity=55;t.execution.record={productName:'<img src=x onerror=alert(1)>'};
 const p=await page({native:true,items:[t]});try{
  await p.w.QcWorkflow.openTask(t.id,'records');assert.equal(p.d.querySelector('#f_qty').value,'55');assert.equal(p.d.querySelector('.qwf-carried img'),null);
  p.d.querySelector('input[name="drawer-result"][value="REJ"]').click();assert.equal(p.w.QcWorkflow.readForm().result,'REJ');
  p.d.querySelector('#f_qty').value='23';p.d.querySelector('#f_qty').dispatchEvent(new p.w.Event('input',{bubbles:true}));assert.equal(p.w.QcWorkflow.readForm().result,'REJ');
 }finally{p.dom.window.close();}
});


test('opening request prevents a new draft or push from replacing in-flight work',async()=>{
 const p=await page({native:true,items:[task()]});try{
  const fetch=p.w.fetch;let release;
  p.w.fetch=async(url,options)=>{if(url==='api/workflow/tasks/task-1')await new Promise(r=>release=r);return fetch(url,options);};
  const pending=p.w.QcWorkflow.openTask('task-1','records');assert.equal(p.w.QcWorkflow.navigationState().busy,true);
  await p.w.QcWorkflow.openNew();p.w.QcWorkflow.preparePush([source]);assert.equal(p.d.querySelector('.qwf-dialog'),null);
  release();await pending;assert.equal(p.w.QcWorkflow.model.task.id,'task-1');assert.ok(p.d.querySelector('.qwf-drawer'));
 }finally{p.dom.window.close();}
});


test('real sidebar navigation hides drawer synchronously before destination rendering and preserves input',async()=>{
 const p=await page({native:true,items:[task('draft')]});try{
  p.w.canView=()=>true;const frames=[];p.w.requestAnimationFrame=fn=>frames.push(fn);
  p.w.realShowPage('records');await p.w.QcWorkflow.openTask('task-1','records');
  const drawer=p.d.querySelector('.qwf-drawer'),qty=p.d.querySelector('#f_qty');qty.value='73';qty.dispatchEvent(new p.w.Event('input',{bubbles:true}));
  const file=p.d.querySelector('[data-files]'),photo=new p.w.File(['test'],'photo.png',{type:'image/png'});Object.defineProperty(file,'files',{value:[photo]});
  p.w.confirm=()=>{throw Error('Navigation must retain input without asking to discard');};
  for(const destination of ['sales-schedule','dashboard','analysis','review','suppliers','daily','import']){
    p.w.realShowPage(destination);assert.equal(drawer.hasAttribute('open'),false,destination);assert.ok(p.d.querySelector('#page-'+destination).classList.contains('active'));
    assert.equal(qty.value,'73');assert.equal(file.files[0],photo);assert.equal(p.w.QcWorkflow.navigationState().dirty,true);
    p.w.realShowPage('records');assert.equal(drawer.hasAttribute('open'),false,'returning alone must not pop the drawer');
    await p.w.QcWorkflow.openTask('task-1','records');assert.equal(drawer.hasAttribute('open'),true);assert.equal(p.d.querySelector('.qwf-drawer'),drawer);
  }
  // No queued destination render has run: hiding cannot depend on RAF or load.
  assert.ok(frames.length>0);assert.equal(p.calls.filter(c=>c.url==='api/workflow/tasks/task-1').length,1);
 }finally{p.dom.window.close();}
});
test('navigation remains blocked while inspection is saving',async()=>{
 const p=await page({native:true,items:[task()]});try{
  p.w.canView=()=>true;p.w.requestAnimationFrame=()=>{};p.w.realShowPage('records');await p.w.QcWorkflow.openTask('task-1','records');
  p.w.QcWorkflow.model.busy=true;p.w.realShowPage('sales-schedule');assert.ok(p.d.querySelector('#page-records').classList.contains('active'));assert.ok(p.d.querySelector('.qwf-drawer').hasAttribute('open'));
 }finally{p.dom.window.close();}
});


test('outside click collapses untouched drawer without discarding or swallowing the target action',async()=>{
 const p=await page({native:true,items:[task('draft')]});try{
  await p.w.QcWorkflow.openTask('task-1','records');const drawer=p.d.querySelector('.qwf-drawer');
  drawer.querySelector('h2').click();assert.ok(drawer.hasAttribute('open'),'inside click must not collapse');
  const outside=p.d.createElement('button');p.d.body.append(outside);let activated=false;outside.onclick=()=>activated=true;
  const calls=p.calls.length;outside.click();assert.equal(drawer.hasAttribute('open'),false);assert.equal(activated,true);assert.equal(p.calls.length,calls);assert.equal(p.d.querySelector('.qwf-drawer'),drawer);
  outside.onclick=()=>p.w.QcWorkflow.openTask('task-1','records');outside.click();assert.ok(drawer.hasAttribute('open'),'resume click must not immediately collapse');
  outside.click();assert.ok(drawer.hasAttribute('open'),'capture preserves same-row reopen action');
 }finally{p.dom.window.close();}
});
test('outside click protects edits, pending files and in-flight work',async()=>{
 const p=await page({native:true,items:[task('draft')]});try{
  await p.w.QcWorkflow.openTask('task-1','records');const drawer=p.d.querySelector('.qwf-drawer'),model=p.w.QcWorkflow.model;
  const qty=p.d.querySelector('#f_qty');qty.value='73';qty.dispatchEvent(new p.w.Event('input',{bubbles:true}));p.d.body.click();assert.ok(drawer.hasAttribute('open'));assert.equal(qty.value,'73');
  model.dirty=false;const caption=p.d.querySelector('[data-caption]');caption.value='现场照片说明';caption.dispatchEvent(new p.w.Event('input',{bubbles:true}));p.d.body.click();assert.ok(drawer.hasAttribute('open'));assert.equal(model.dirty,true);
  model.dirty=false;model.busy=true;p.d.body.click();assert.ok(drawer.hasAttribute('open'));model.busy=false;model.opening=true;p.d.body.click();assert.ok(drawer.hasAttribute('open'));model.opening=false;
  const input=p.d.querySelector('[data-files]');Object.defineProperty(input,'files',{value:[new p.w.File(['test'],'photo.png',{type:'image/png'})]});p.d.body.click();assert.ok(drawer.hasAttribute('open'));
 }finally{p.dom.window.close();}
});
test('outside handler is removed on close and does not affect supervisor dialogs',async()=>{
 const p=await page({native:true,items:[task('pending')],review:true});try{
  await p.w.QcWorkflow.openTask('task-1','records');p.w.QcWorkflow.close();
  await p.w.QcWorkflow.openTask('task-1','review');const dialog=p.d.querySelector('.qwf-dialog');p.d.body.click();assert.ok(dialog.hasAttribute('open'));assert.equal(dialog.classList.contains('qwf-drawer'),false);
 }finally{p.dom.window.close();}
});


test('inspection list uses schedule ranges without replacing incoming, actual or modified dates',async()=>{
 const records=[31,32,33].map(id=>({id,status:'approved',date:'2025-01-01',inspDate:'2025-02-02',updatedAt:'2026-10-'+(id-5),productNo:String(id)}));
 const p=await page({native:true,legacyRecords:records});try{
  p.w.__QC_INSPECTION_PLANS={'31':{from:'2026-10-27',to:'2026-10-29'},'32':{from:'2026-10-30',to:'2026-10-30'}};
  const ids=()=>Array.from(p.d.querySelectorAll('#recordsTable tbody tr[data-id]'),r=>Number(r.dataset.id));
  p.w.filterRecords();assert.equal(p.d.querySelectorAll('#recordsTable thead th').length,20);
  assert.equal(p.d.querySelectorAll('#recordsTable thead th')[2].textContent,'验货日期');
  assert.equal(p.d.querySelector('[data-id="31"] td:nth-child(3)').textContent,'10月27–29日');
  assert.match(p.d.querySelector('[data-id="31"] td:nth-child(3) span').title,/2026-10-27 至 2026-10-29/);
  assert.equal(p.d.querySelector('[data-id="32"] td:nth-child(3)').textContent,'10月30日');
  assert.match(p.d.querySelector('[data-id="32"] td:nth-child(3) span').title,/2026-10-30/);
  assert.equal(p.d.querySelector('[data-id="31"] td:nth-child(4)').textContent,'2026-10-26');
  for(const date of ['2026-10-27','2026-10-28','2026-10-29']){
   p.d.getElementById('filterDateFrom').value=date;p.d.getElementById('filterDateTo').value=date;p.w.filterRecords();assert.deepEqual(ids(),[31]);
  }
  p.d.getElementById('filterDateFrom').value='';p.d.getElementById('filterDateTo').value='';
  p.d.getElementById('filterSort').value='date-asc';p.w.filterRecords();assert.deepEqual(ids(),[31,32,33]);
  p.d.getElementById('filterSort').value='date-desc';p.w.filterRecords();assert.deepEqual(ids(),[32,31,33]);
  assert.equal(p.w.inspectionPlanRange(records[2]),null);
  assert.equal(p.w.inspectionPlanRange({inspectionPlan:{from:'2026-02-30'}}),null);
  assert.equal(records[0].date,'2025-01-01');assert.equal(records[0].inspDate,'2025-02-02');
  assert.match(p.w._recordsExportQuery(),/dateBasis=inspection-plan/);
 }finally{p.dom.window.close();}
});
test('formal list plan follows current customer schedule, not actual or task confirmation date',async()=>{
 const t=task();t.currentSource={...t.source,dateFrom:'2026-11-01',dateTo:'2026-11-03'};t.execution.actualDate='2026-10-29';
 const p=await page({native:true,items:[t]});try{
  const r=p.w.QcWorkflow.recordItems()[0];assert.deepEqual(copy(r.inspectionPlan),{from:'2026-11-01',to:'2026-11-03'});
  assert.equal(p.w.inspectionPlanText(r),'11月1–3日');
 }finally{p.dom.window.close();}
});


test('toolbar date drafts validate before applying and reset restores all filters',async()=>{
 const p=await page({native:true,items:[task()]});try{
  const d=p.d,w=p.w;
  d.getElementById('recordsDateFilter').open=true;w.prepareRecordsDates();
  d.getElementById('recordsDateDraftFrom').value='2026-10-30';
  d.getElementById('recordsDateDraftTo').value='2026-10-27';
  w.applyRecordsDates();
  assert.equal(d.getElementById('filterDateFrom').value,'');
  assert.equal(d.getElementById('recordsDateFilter').open,true);
  assert.equal(d.getElementById('recordsDateError').hidden,false);
  d.getElementById('recordsDateDraftFrom').value='2026-10-26';
  w.applyRecordsDates();
  assert.equal(d.getElementById('filterDateFrom').value,'2026-10-26');
  assert.equal(d.getElementById('recordsDateFilter').open,false);
  assert.match(d.getElementById('recordsDateLabel').textContent,/2026-10-26 至 2026-10-27/);
  d.getElementById('recordsDateFilter').open=true;w.prepareRecordsDates();
  d.getElementById('recordsDateDraftFrom').value='2026-12-31';
  d.body.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
  assert.equal(d.getElementById('recordsDateFilter').open,false);
  assert.equal(d.getElementById('filterDateFrom').value,'2026-10-26');
  d.getElementById('searchInput').value='no match';d.getElementById('filterResult').value='REJ';d.getElementById('filterSort').value='date-asc';
  w.resetRecordsFilters();
  assert.equal(d.getElementById('recordCount').textContent,'共 1 条');
  assert.equal(d.getElementById('recordsDateLabel').textContent,'不限验货日期');
  assert.equal(d.getElementById('filterSort').value,'mod-desc');
  let message='';w.showToast=text=>{message=text;};const calls=p.calls.length;
  w.requestInspectionExcel();assert.match(message,/待配置模板/);assert.equal(p.calls.length,calls);
 }finally{p.dom.window.close();}
});


test('select all uses current filters, supports half/none, and blocks cancelled or unauthorized sources',async()=>{
 const sources=[{...source,id:'a',productNo:'A-1'},{...source,id:'b',productNo:'A-2'},{...source,id:'c',productNo:'B-1'},{...source,id:'x',sourceStatus:'cancelled'}];
 const p=await page({sources});try{
  await p.w.renderSalesSchedule();const all=p.d.getElementById('qsSelectAll'),push=p.d.getElementById('qsPush');all.click();
  assert.equal(p.d.querySelectorAll('[data-pick]:checked').length,3);assert.match(push.textContent,/（3）/);
  p.d.querySelector('[data-pick="a"]').click();assert.equal(all.indeterminate,true);all.click();assert.equal(all.checked,true);all.click();assert.equal(push.disabled,true);
  const search=p.d.getElementById('qsSearch');search.value='A-';search.dispatchEvent(new p.w.Event('input'));all.click();assert.equal(p.d.querySelectorAll('[data-pick]:checked').length,2);
  push.click();await settled(p);
  assert.deepEqual(p.calls.find(c=>c.url==='api/workflow/tasks'&&c.body).body.items.map(x=>x.sourceId).sort(),['a','b']);
  search.value='missing-order';search.dispatchEvent(new p.w.Event('input'));assert.equal(all.disabled,true);assert.equal(push.disabled,true);
  search.value='';search.dispatchEvent(new p.w.Event('input'));p.w.__QC_NEXUS.workflow.create=false;await p.w.renderSalesSchedule();assert.equal(all.disabled,true);assert.equal(push.disabled,true);
 }finally{p.dom.window.close();}
});

test('all 47 schedule rows directly enter one batch request',async()=>{
 const p=await page({sources:Array.from({length:47},(_,i)=>({...source,id:'s-'+i,productNo:'SKU-'+i}))});try{
  await p.w.renderSalesSchedule();p.d.getElementById('qsSelectAll').click();assert.match(p.d.getElementById('qsPush').textContent,/（47）/);p.d.getElementById('qsPush').click();
  assert.equal(p.d.querySelector('.qwf-dialog'),null);await settled(p);
  const calls=p.calls.filter(c=>c.url==='api/workflow/tasks'&&c.body);assert.equal(calls.length,1);assert.equal(new Set(calls[0].body.items.map(x=>x.sourceId)).size,47);
 }finally{p.dom.window.close();}
});


test('direct push uses explicit methods and skips incomplete records',async()=>{
 const p=await page({sources:[{...source,id:'i',agency:'行验'},{...source,id:'e',agency:'客验'},{...source,id:'u',agency:'SGS'},{...source,id:'no-date',dateFrom:''},{...source,id:'zero',quantity:'0'}]});try{
  await p.w.renderSalesSchedule();p.d.getElementById('qsSelectAll').click();p.d.getElementById('qsPush').click();
  await settled(p);const items=p.calls.find(c=>c.url==='api/workflow/tasks'&&c.body).body.items;
  assert.deepEqual(items.map(x=>[x.sourceId,x.method]),[['i','internal'],['e','external']]);assert.equal(p.d.querySelector('.qwf-dialog'),null);
 }finally{p.dom.window.close();}
});


test('47 selected with one missing date pushes exactly 46 without a dialog',async()=>{
 const sources=Array.from({length:47},(_,i)=>({...source,id:'s-'+i,dateFrom:i===46?'':source.dateFrom}));const p=await page({sources});try{
  await p.w.renderSalesSchedule();p.d.getElementById('qsSelectAll').click();p.d.getElementById('qsPush').click();await settled(p);
  const items=p.calls.find(c=>c.url==='api/workflow/tasks'&&c.body).body.items;assert.equal(items.length,46);assert.equal(items.some(x=>x.sourceId==='s-46'),false);assert.equal(p.d.querySelector('.qwf-dialog'),null);
 }finally{p.dom.window.close();}
});


test('missing-date-only selection reports exclusion without creating any task',async()=>{
 const p=await page();try{
  const messages=[];p.w.showToast=text=>messages.push(text);await p.w.QcWorkflow.preparePush([{...source,dateFrom:''}]);
  assert.equal(p.calls.filter(c=>c.url==='api/workflow/tasks'&&c.body).length,0);assert.match(messages[0],/缺少计划日期/);assert.equal(p.d.querySelector('.qwf-dialog'),null);
 }finally{p.dom.window.close();}
});
