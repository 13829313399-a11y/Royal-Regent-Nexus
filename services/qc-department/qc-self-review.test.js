'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');const tick=()=>new Promise(r=>setTimeout(r,10));
async function page(){
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window,calls=[];
 w.requestAnimationFrame=fn=>w.setTimeout(fn,0);Object.defineProperty(w.document,'hidden',{value:false});w.document.getElementById('page-review').classList.add('active');
 w.__QC_NEXUS={workflow:{edit:true},exportAllowed:false};w.showToast=()=>{};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 const rows=['a','b','c'].map((id,i)=>({id,customer:'客户'+i,poNo:'PO'+i,productNo:'ITEM'+i,dateFrom:'2026-11-03',dateTo:'2026-11-03',result:'PASS',remark:'原备注',improvement:'原措施',photos:[],revision:1,submittedAt:'2026-11-01T17:00:00Z',reviewState:'pending',flowVersion:2,lastActor:{name:'后台用户'},lastLocation:'验货台',lastChangedAt:'2026-11-01T17:00:00Z'}));
 let failId='',eventId=0;const events=[],seen=new Set();w.fetch=async(url,opts={})=>{
  const body=opts.body?JSON.parse(opts.body):null;calls.push({url,body});let value;
  if(url.endsWith('/notifications'))value={items:events.filter(e=>!seen.has(e.eventId)&&rows.find(r=>r.id===e.entryId)?.reviewState==='pending')};
  else if(url.endsWith('/notifications/shown')){body.eventIds.forEach(id=>seen.add(id));value={shown:body.eventIds};}
  else if(url.endsWith('/return-to-inspection')){const row=rows.find(r=>r.id===url.split('/').at(-2));assert.equal(body.revision,row.revision);row.revision++;row.reviewState='returned_to_inspection';value={item:structuredClone(row),eventId:100};}
  else if(url.endsWith('/entries'))value={results:['PASS','FAIL','PENDING','LG'],items:url.includes('review/')?structuredClone(rows):[],columns:['customer','poNo','date','result','remark','photos','improvement','submit'].map(key=>({key,label:key}))};
  else if(url.endsWith('/save')){const row=rows.find(r=>r.id===url.split('/').at(-2));assert.equal(row.revision,body.revision);Object.assign(row,{...body,...(body.inspectionExecution?{inspectionExecution:{...row.inspectionExecution,...body.inspectionExecution}}:{})},{revision:row.revision+1,lastLocation:'审核中心 · 待审核'});value=structuredClone(row);}
  else if(url.endsWith('/photos')){const row=rows.find(r=>r.id===url.split('/').at(-2));assert.equal(row.revision,body.revision);row.photos.push({id:'p-'+row.photos.length,name:body.name});row.revision++;value=structuredClone(row);}
  else if(/review\/(confirm|revoke)$/.test(url)){
   const results=body.entries.map(e=>{if(e.id===failId)return{id:e.id,ok:false,message:'并发版本变化',status:409};const row=rows.find(r=>r.id===e.id);assert.equal(row.revision,e.revision);Object.assign(row,{revision:row.revision+1,reviewState:url.endsWith('confirm')?'approved':'pending',confirmedAt:'2026-11-01T17:25:00Z',lastActor:{name:'后台用户'},lastLocation:url.endsWith('confirm')?'审核中心 · 待审核':'审核中心 · 已审核'});if(url.endsWith('revoke'))row.lastReversal={eventId:++eventId,entryId:row.id,customer:row.customer,poNo:row.poNo,at:'2026-11-01T17:26:00Z',actor:{name:'后台用户'},location:'审核中心 · 已审核',reason:body.reason};if(url.endsWith('revoke'))events.push(structuredClone(row.lastReversal));return{id:e.id,ok:true,item:structuredClone(row),...(url.endsWith('revoke')?{reversal:structuredClone(row.lastReversal)}:{})};});value={results,succeeded:results.filter(r=>r.ok).length,failed:results.filter(r=>!r.ok).length};
  }else if(url.endsWith('/audit'))value={items:[]};else throw Error(url);
  return{ok:true,json:async()=>value};
 };
 for(const file of ['qc-photo-paste.js','qc-inspection-audit.js','qc-inspection-sheet.js'])w.eval(fs.readFileSync(path.join(__dirname,file),'utf8'));
 await tick();await w.QcInspectionSheet.loadReview('pending');return{dom,w,d:w.document,rows,calls,set failId(v){failId=v;}};
}
test('two tabs, full fields, server audit hints and read-only confirmed rows',async()=>{
 const p=await page();try{
  assert.equal(p.d.getElementById('reviewTabRejected'),null);assert.equal(p.d.querySelectorAll('#reviewTableWrap tbody tr').length,3);
  for(const field of ['sourceNote','submittedAt','confirmedAt','lastChangedAt','lastActor.name','inspectionExecution.reportNo'])assert.ok(p.d.querySelector('th[data-column="'+field+'"]'));
  assert.match(p.d.querySelector('[data-audit]').title,/后台用户/);assert.match(p.d.querySelector('[data-audit]').title,/2026\/11\/02 01:00/);
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelectorAll('#reviewTableWrap tbody tr').length,1);
  assert.ok(p.d.querySelector('[data-remark]').disabled);assert.equal(p.d.querySelector('[data-files]'),null);assert.ok(p.d.querySelector('[data-revoke]'));
 }finally{p.dom.window.close();}
});
test('batch confirmation flushes text, uses explicit selection and reports partial failure',async()=>{
 const p=await page();try{
  for(const id of ['a','b'])p.d.querySelector('[data-review-check="'+id+'"]').click();p.failId='b';
  p.w.QcInspectionSheet.edit('a','remark','还未防抖的备注');p.d.getElementById('qis-review-batch').click();
  assert.match(p.d.querySelector('dialog').textContent,/2 条/);p.d.querySelector('[data-execute]').click();await tick();await tick();
  const req=p.calls.find(c=>c.url.endsWith('review/confirm'));assert.deepEqual(req.body.entries.map(e=>e.id),['a','b']);assert.equal(req.body.entries[0].revision,2);
  assert.equal(p.rows[0].remark,'还未防抖的备注');assert.equal(p.rows[0].reviewState,'approved');assert.equal(p.rows[1].reviewState,'pending');assert.equal(p.rows[2].reviewState,'pending');
  assert.match(p.d.querySelector('[data-feedback]').textContent,/成功 1 条，失败 1 条/);assert.ok(p.w.QcInspectionSheet.model.checked.has('b'));
 }finally{p.dom.window.close();}
});
test('changing filter clears selection; all means only visible rows',async()=>{
 const p=await page();try{
  p.d.getElementById('qis-review-all').click();assert.equal(p.w.QcInspectionSheet.model.checked.size,3);
  const search=p.d.querySelector('[data-rfilter=search]');search.value='PO1';search.dispatchEvent(new p.w.Event('input'));assert.equal(p.w.QcInspectionSheet.model.checked.size,0);
  p.d.getElementById('qis-review-all').click();assert.deepEqual([...p.w.QcInspectionSheet.model.checked],['b']);
 }finally{p.dom.window.close();}
});

test('confirmation active class and count follow zero, one, two, three and cancelled selections',async()=>{
 const p=await page();try{
  const button=p.d.getElementById('qis-review-batch');assert.ok(button.disabled);assert.ok(!button.classList.contains('qis-confirm-ready'));
  for(const [i,id] of ['a','b','c'].entries()){p.d.querySelector('[data-review-check='+id+']').click();assert.equal(button.disabled,false);assert.ok(button.classList.contains('qis-confirm-ready'));assert.equal(button.textContent,'审核确认所选（'+(i+1)+'）');}
  p.d.getElementById('qis-review-all').click();assert.ok(button.disabled);assert.ok(!button.classList.contains('qis-confirm-ready'));
 }finally{p.dom.window.close();}
});
test('Beijing cross-day timestamps have no current-time fallback',async()=>{
 const p=await page();try{assert.equal(p.w.QcInspectionAudit.time('2026-11-01T17:05:00Z'),'2026/11/02 01:05:00');assert.equal(p.w.QcInspectionAudit.time(''),'暂无记录');assert.equal(p.w.QcInspectionAudit.time('bad'),'暂无记录');}finally{p.dom.window.close();}
});

test('LG uses server result contract and legacy completed rows expose both revoke entrances',async()=>{
 const p=await page();try{
  assert.deepEqual([...p.d.querySelector('[data-result]').options].map(o=>o.value),['','PASS','FAIL','PENDING','LG']);
  p.w.QcInspectionSheet.edit('a','result','LG');await p.w.QcInspectionSheet.flush();assert.equal(p.rows[0].result,'LG');
  p.rows[0].legacyCompleted=true;p.rows[0].reviewState='';await p.w.QcInspectionSheet.loadReview('approved');
  p.d.querySelector('[data-review-check=a]').click();assert.equal(p.d.getElementById('qis-review-batch').disabled,false);
  p.d.querySelector('[data-revoke=a]').click();const dialog=p.d.querySelector('dialog');assert.match(dialog.textContent,/PO0.*LG/);assert.ok(dialog.querySelector('[data-cancel]'));
  dialog.querySelector('[data-cancel]').click();assert.equal(p.calls.filter(c=>c.url.endsWith('/revoke')).length,0);
 }finally{p.dom.window.close();}
});

test('row actions stay under frozen PO and retain the original confirmation flow',async()=>{
 const p=await page();try{
  assert.equal(p.d.querySelector('th[data-column=submit]'),null);
  const pending=p.d.querySelector('[data-confirm=a]');assert.equal(pending.closest('td').dataset.column,'poNo');
  assert.equal(p.d.querySelector('[data-audit]').closest('td').dataset.column,'customer');
  pending.click();p.d.querySelector('[data-execute]').click();await tick();await tick();
  const confirm=p.calls.find(c=>c.url.endsWith('review/confirm'));assert.deepEqual(confirm.body.entries.map(x=>x.id),['a']);
  await p.w.QcInspectionSheet.loadReview('approved');
  const revoke=p.d.querySelector('[data-revoke=a]');assert.equal(revoke.closest('td').dataset.column,'poNo');assert.equal(p.d.querySelectorAll('[data-revoke=a]').length,1);
  revoke.click();p.d.querySelector('[data-reason]').value='可见入口\n保留原流程';p.d.querySelector('[data-execute]').click();await tick();await tick();
  const req=p.calls.find(c=>c.url.endsWith('review/revoke'));assert.equal(req.body.reason,'可见入口\n保留原流程');assert.equal(p.rows[0].reviewState,'pending');
 }finally{p.dom.window.close();}
});


test('revoke receipt is centered, lists successes and failures, and return badge survives reload',async()=>{
 const p=await page();try{
  p.rows.forEach(r=>r.reviewState='approved');await p.w.QcInspectionSheet.loadReview('approved');p.failId='c';
  p.d.getElementById('qis-review-all').click();p.d.getElementById('qis-review-batch').click();p.d.querySelector('[data-execute]').click();await tick();await tick();
  assert.equal(p.d.querySelector('.qis-reversal-notice'),null);assert.match(p.d.querySelector('dialog').textContent,/失败 1 条/);p.d.querySelector('dialog [data-close]')?.click();await p.w.QcInspectionSheet.loadReview('pending');await tick();await tick();
  const dialog=p.d.querySelector('.qis-reversal-notice');assert.ok(dialog);assert.equal(dialog.querySelectorAll('.qis-reversal-item').length,2);assert.match(dialog.textContent,/成功退回待审核 2 条/);
  assert.match(dialog.textContent,/2026\/11\/02 01:26:00/);assert.doesNotMatch(dialog.textContent,/反审核说明|未填写/);
  dialog.querySelector('[data-close]').click();await new Promise(resolve=>setTimeout(resolve,150));await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelectorAll('[data-reversal]').length,2);assert.equal(p.d.querySelector('.qis-reversal-notice'),null);
  p.d.querySelector('[data-reversal=a]').click();assert.match(p.d.querySelector('dialog').textContent,/后台用户.*审核中心/s);p.d.querySelector('[data-close]').click();
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelector('[data-reversal=a]'),null);
 }finally{p.dom.window.close();}
});

test('nonempty reversal reason is escaped and displayed without trusting browser time',async()=>{
 const p=await page();try{
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');p.d.querySelector('[data-revoke=a]').click();
  p.d.querySelector('[data-reason]').value='复核 <img src=x onerror=alert(1)>';p.d.querySelector('[data-execute]').click();await tick();await tick();
  assert.equal(p.d.querySelector('.qis-reversal-notice'),null);await p.w.QcInspectionSheet.loadReview('pending');await tick();await tick();const dialog=p.d.querySelector('.qis-reversal-notice');assert.match(dialog.textContent,/反审核说明：复核 <img/);assert.equal(dialog.querySelector('img'),null);
 }finally{p.dom.window.close();}
});

test('pending supplemental fields autosave, preserve identity and notes, then become readonly after confirmation',async()=>{
 const p=await page();try{
  const node=p.d.querySelector('[data-entry=a]'),input=node.querySelector('[data-review-field=responsible]');assert.equal(input.type,'text');assert.equal(input.maxLength,200);
  input.focus();input.value='负责人甲';input.dispatchEvent(new p.w.Event('input'));p.w.QcInspectionSheet.render();assert.equal(p.d.activeElement.dataset.reviewField,'responsible');assert.equal(p.d.activeElement.value,'负责人甲');
  await p.w.QcInspectionSheet.flush();const save=p.calls.find(c=>c.url.endsWith('/save'));assert.equal(save.body.responsible,'负责人甲');assert.equal(save.body.remark,'原备注');assert.equal(save.body.improvement,'原措施');assert.ok(!('poNo' in save.body));
  await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-review-field=responsible]').value,'负责人甲');
  p.d.querySelector('[data-confirm=a]').click();p.d.querySelector('[data-execute]').click();await tick();await tick();assert.equal(p.rows[0].responsible,'负责人甲');
  await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelector('[data-review-field]'),null);assert.match(p.d.querySelector('[data-column=responsible]').parentElement.parentElement.textContent,/责任人/);
 }finally{p.dom.window.close();}
});

test('pending execution editors autosave partial fields, retain zero, and leave source status readonly',async()=>{
 const p=await page();try{
  const row=p.d.querySelector('[data-entry=a]');
  for(const key of ['actualDate','actualQuantity','inspector','sampleQuantity','institution','reportNo','reportMissingReason','resultExplanation'])assert.ok(row.querySelector('[data-execution-field="'+key+'"]'),key);
  assert.equal(row.querySelector('[data-review-field=responsible]').size,1);
  assert.equal(row.querySelector('[data-column="sourceRecord.sourceStatus"] input'),null);
  const qty=row.querySelector('[data-execution-field=sampleQuantity]');qty.value='0';qty.dispatchEvent(new p.w.Event('input'));qty.focus();p.w.QcInspectionSheet.render();assert.equal(p.d.activeElement.dataset.executionField,'sampleQuantity');assert.equal(p.d.activeElement.value,'0');
  await p.w.QcInspectionSheet.flush();const sent=p.calls.find(c=>c.url.endsWith('/save')).body;assert.deepEqual(sent.inspectionExecution,{sampleQuantity:'0'});assert.equal(sent.remark,'原备注');
  await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-execution-field=sampleQuantity]').value,'0');
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelector('[data-execution-field]'),null);assert.ok(p.d.querySelector('[data-detail=defects]'));
 }finally{p.dom.window.close();}
});
test('structured details add/remove/save and cancel keep their own row and revision queue',async()=>{
 const p=await page();try{
  p.d.querySelector('[data-entry=a] [data-detail=defects]').click();p.d.querySelector('[data-detail-add]').click();
  const set=(k,value)=>{const n=p.d.querySelector('[data-detail-row="0"][data-detail-key="'+k+'"]');n.value=value;n.dispatchEvent(new p.w.Event('input'));};
  set('desc','包装压痕');set('qty','2');set('level','MIN 2.5');set('remark','测试明细');
  p.d.querySelector('[data-detail-add]').click();p.d.querySelector('[data-detail-remove="1"]').click();assert.equal(p.d.querySelectorAll('[data-detail-remove]').length,1);
  p.d.querySelector('[data-detail-save]').click();await tick();await tick();assert.equal(p.d.querySelector('dialog'),null);
  assert.equal(p.rows[0].inspectionExecution.defects[0].qty,'2');assert.equal(p.rows[1].inspectionExecution,undefined);
  await p.w.QcInspectionSheet.loadReview('pending');p.d.querySelector('[data-entry=a] [data-detail=defects]').click();assert.equal(p.d.querySelector('[data-detail-key=desc]').value,'包装压痕');
  p.d.querySelector('[data-detail-remove]').click();p.d.querySelector('[data-close]').click();assert.equal(p.rows[0].inspectionExecution.defects.length,1);
  p.d.querySelector('[data-entry=a] [data-detail=defects]').click();p.d.querySelector('[data-detail-remove]').click();p.d.querySelector('[data-detail-save]').click();await tick();await tick();assert.equal(p.rows[0].inspectionExecution.defects.length,0);
  p.d.querySelector('[data-entry=a] [data-detail=measurements]').click();p.d.querySelector('[data-detail-add]').click();set('item','长度');set('standard','100±1 mm');set('values','100.2 mm');set('result','PASS');set('remark','测量备注');p.d.querySelector('[data-detail-save]').click();await tick();await tick();assert.equal(p.rows[0].inspectionExecution.measurements[0].values,'100.2 mm');
  assert.equal(p.rows[0].reviewState,'pending');assert.ok(!p.calls.some(c=>/review\/(confirm|revoke)$/.test(c.url)));
 }finally{p.dom.window.close();}
});
test('review image paste uses the pending endpoint and never changes approved rows',async()=>{
 const p=await page();try{
  p.d.getElementById('page-review').classList.add('active');const paste=target=>{const event=new p.w.Event('paste',{bubbles:true,cancelable:true});Object.defineProperty(event,'clipboardData',{value:{files:[new p.w.File(['x'],'review.png',{type:'image/png'})]}});target.dispatchEvent(event);return event;};
  p.d.querySelector('[data-entry="b"]').click();paste(p.d.body);await p.w.QcInspectionSheet.flush();assert.equal(p.rows[1].photos.length,1);assert.ok(p.calls.some(c=>c.url==='api/inspection-sheet/review/entries/b/photos'));assert.equal(p.rows[0].photos.length,0);
  p.rows[1].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');p.d.querySelector('[data-entry="b"]').click();paste(p.d.body);await tick();assert.equal(p.calls.filter(c=>c.url.endsWith('/photos')).length,1);assert.equal(p.rows[1].reviewState,'approved');
 }finally{p.dom.window.close();}
});

test('return button is next to confirm, cancel writes nothing, confirmed return uses same row',async()=>{
 const p=await page();try{const a=p.d.querySelector('[data-confirm=a]'),b=p.d.querySelector('[data-return=a]');assert.equal(a.nextElementSibling,b);assert.ok(b.classList.contains('qis-return-action'));b.click();assert.match(p.d.querySelector('dialog').textContent,/客户：客户0.*PO：PO0/s);const before=p.calls.length;p.d.querySelector('[data-cancel]').click();assert.equal(p.calls.length,before);assert.equal(p.rows[0].reviewState,'pending');b.click();p.d.querySelector('[data-return-confirm]').click();await tick();await tick();assert.equal(p.rows[0].reviewState,'returned_to_inspection');assert.equal(p.d.querySelector('[data-entry=a]'),null);assert.equal(p.rows[1].reviewState,'pending');}finally{p.dom.window.close();}
});
test('customer requirements and ship date use autosave, valid editors and readonly approval',async()=>{
 const p=await page();try{const row=p.d.querySelector('[data-entry=a]');assert.equal(row.querySelector('[data-review-field=customerRequirements]').tagName,'TEXTAREA');assert.equal(row.querySelector('[data-review-field=shipDate]').type,'date');p.w.QcInspectionSheet.edit('a','customerRequirements','客户补录');p.w.QcInspectionSheet.edit('a','shipDate','2026-12-20');await p.w.QcInspectionSheet.flush();assert.equal(p.rows[0].shipDate,'2026-12-20');await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-review-field=customerRequirements]').value,'客户补录');p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelector('[data-review-field=shipDate]'),null);}finally{p.dom.window.close();}
});
test('cancelled sources never show a return-to-workbench action',async()=>{
 const p=await page();try{p.rows[0].sourceCancelled=true;await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-return=a]'),null);assert.ok(p.d.querySelector('[data-return=b]'));}finally{p.dom.window.close();}
});

test('review order supplements autosave, keep leading zeroes and zero quantity, and lock approved rows',async()=>{
 const p=await page();try{
  p.rows[0].contractNo='SOURCE-01';p.rows[0].customerCode='0007';p.rows[0].shippedQuantity=0;
  p.rows[0].sourceRecord={contractNo:'SOURCE-01',customerCode:'0007',shippedQuantity:0};
  await p.w.QcInspectionSheet.loadReview('pending');
  const row=p.d.querySelector('[data-entry=a]');assert.equal(row.querySelector('[data-review-field=shippedQuantity]').value,'0');
  for(const [key,value] of Object.entries({contractNo:'001-CONTRACT',customerCode:'00042',shippedQuantity:'12.5'})){
   const input=row.querySelector('[data-review-field='+key+']');assert.equal(input.size,1);assert.equal(input.type,key==='shippedQuantity'?'number':'text');
   input.value=value;input.dispatchEvent(new p.w.Event('input'));
  }
  await p.w.QcInspectionSheet.flush();await p.w.QcInspectionSheet.loadReview('pending');
  for(const [key,value] of Object.entries({contractNo:'001-CONTRACT',customerCode:'00042',shippedQuantity:'12.5'}))assert.equal(p.d.querySelector('[data-entry=a] [data-review-field='+key+']').value,value);
  assert.deepEqual(p.rows[0].sourceRecord,{contractNo:'SOURCE-01',customerCode:'0007',shippedQuantity:0});
  assert.ok(!('sourceRecord' in p.calls.filter(c=>c.url.endsWith('/save')).at(-1).body));
  p.w.QcInspectionSheet.edit('a','contractNo','');p.w.QcInspectionSheet.edit('a','shippedQuantity','0');await p.w.QcInspectionSheet.flush();
  await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-review-field=contractNo]').value,'');assert.equal(p.d.querySelector('[data-entry=a] [data-review-field=shippedQuantity]').value,'0');
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');
  assert.equal(p.d.querySelector('[data-review-field=contractNo]'),null);assert.equal(p.d.querySelector('[data-entry=a] [data-column=customerCode]').textContent,'00042');assert.equal(p.d.querySelector('[data-entry=a] [data-column=shippedQuantity]').textContent,'0');
 }finally{p.dom.window.close();}
});

test('order supplement audit uses business labels and keeps before and after values',async()=>{
 const p=await page();try{
  p.w.fetch=async()=>({ok:true,json:async()=>({items:[{id:1,action:'save',at:'2026-11-03T01:00:00Z',actor:{name:'测试用户'},location:'审核中心 · 待审核',changes:{contractNo:{before:'SRC',after:'001'},customerCode:{before:'0007',after:'00042'},shippedQuantity:{before:'12.5',after:'0'}}}]})});
  await p.w.QcInspectionAudit.show('a');const history=p.d.querySelector('.qia-event').textContent;
  assert.match(history,/合同号：SRC → 001/);assert.match(history,/客户编码：0007 → 00042/);assert.match(history,/已出货数量：12.5 → 0/);
 }finally{p.dom.window.close();}
});
