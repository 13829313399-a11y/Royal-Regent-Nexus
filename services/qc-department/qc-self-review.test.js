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
  else if(url.endsWith('/entries'))value={results:['PASS','FAIL','PENDING','LG'],items:url.includes('review/')?structuredClone(rows):[],columns:['date','customer','poNo','country','productNo','productName','quantity','unitsPerCarton','cartonCount','production','agency','customerPo','completion','result','remark','photos','improvement','submit'].map(key=>({key,label:key}))};
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
test('review uses the fixed workbench order followed by supplements for every row, retaining frozen actions',async()=>{
 const p=await page();try{
  p.rows[1].inspectionExecution={defects:[{desc:'标签错位',qty:'0'}]};p.rows[2].remark='长备注';await p.w.QcInspectionSheet.loadReview('pending');
  const expected=['date','customer','poNo','actualDate','country','productNo','productName','quantity','unitsPerCarton','cartonCount','production','agency','customerPo','completion','result','inspectionProblem','improvement','photos','remark','actualQuantity','inspectionExecution.sampleQuantity','inspector','responsible','firstResponsible','secondResponsible','inspectionExecution.reportNo','reportStatus','inspectionExecution.institution','inspectionFactory','contractNo','otherRemark','inspectionExecution.defects','submittedAt','confirmedAt','reviewState','lastChangedAt','lastLocation','lastActor.name'];
  assert.deepEqual([...p.d.querySelectorAll('#reviewTableWrap th[data-column]')].map(c=>c.dataset.column),expected);
  for(const row of p.d.querySelectorAll('#reviewTableWrap tr[data-entry]'))assert.deepEqual([...row.querySelectorAll('td[data-column]')].map(c=>c.dataset.column),expected);
  assert.equal(p.d.querySelector('[data-confirm=a]').closest('td').dataset.column,'poNo');assert.equal(p.d.querySelector('[data-audit=a]').closest('td').dataset.column,'customer');
  assert.equal(p.d.querySelector('[data-entry=a] [data-execution-field=actualDate]').closest('td').nextElementSibling.dataset.column,'country');
 }finally{p.dom.window.close();}
});
test('active-only, technical-only and repeated main content hide source entrance without deleting audit or source data',async()=>{
 const p=await page();try{
  p.rows[0].sourceRecord={sourceStatus:'active',sourceId:'technical',customer:'客户0',poNo:'PO0'};p.rows[0].sourceNote=' 原备注 ';
  p.rows[1].sourceRecord={sourceStatus:' ACTIVE ',id:'system-id'};p.rows[2].sourceRecord={sourceStatus:'',customerCode:'  '};
  const before=structuredClone(p.rows);await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-review-info]'),null);
  assert.equal(p.d.querySelectorAll('[data-audit]').length,3);p.d.querySelector('[data-audit=a]').click();await tick();assert.ok(p.calls.some(c=>c.url.endsWith('/audit')));assert.deepEqual(p.rows,before);
 }finally{p.dom.window.close();}
});
test('source entrance is removed even for meaningful history, while pending and approved data and audit remain',async()=>{
 const p=await page();try{
  Object.assign(p.rows[0],{sourceRecord:{sourceStatus:'active',customerCode:'00042',shipDate:'2026-11-20',shippedQuantity:0},sourceNote:'原始业务备注',customerCode:'旧编码',customerRequirements:'历史客户要求'});
  p.rows[1].sourceRecord={sourceStatus:'cancelled'};p.rows[2].inspectionExecution={reportMissingReason:'等待报告'};
  const before=structuredClone(p.rows);await p.w.QcInspectionSheet.loadReview('pending');
  assert.equal(p.d.querySelector('[data-review-info]'),null);assert.equal(p.d.querySelectorAll('[data-audit]').length,3);
  p.d.querySelector('[data-audit=a]').click();await tick();assert.ok(p.calls.some(c=>c.url.endsWith('/audit')));assert.deepEqual(p.rows,before);
  p.d.querySelector('dialog [data-close]').click();p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');
  assert.equal(p.d.querySelector('[data-review-info]'),null);assert.ok(p.d.querySelector('[data-audit=a]'));assert.ok(p.d.querySelector('[data-revoke=a]'));assert.equal(p.d.querySelector('[data-entry=a] [data-remark]').disabled,true);
  assert.deepEqual(p.rows[0].sourceRecord,before[0].sourceRecord);assert.equal(p.rows[0].customerCode,'旧编码');assert.equal(p.rows[0].customerRequirements,'历史客户要求');
 }finally{p.dom.window.close();}
});
test('two tabs, full fields, server audit hints and read-only confirmed rows',async()=>{
 const p=await page();try{
  assert.equal(p.d.getElementById('reviewTabRejected'),null);assert.equal(p.d.querySelectorAll('#reviewTableWrap tbody tr').length,3);
  for(const field of ['submittedAt','confirmedAt','lastChangedAt','lastActor.name','inspectionExecution.reportNo'])assert.ok(p.d.querySelector('th[data-column="'+field+'"]'));
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
  for(const key of ['actualDate','actualQuantity','inspector','sampleQuantity','institution','reportNo'])assert.ok(row.querySelector('[data-execution-field="'+key+'"]'),key);
  assert.equal(row.querySelector('[data-review-field=responsible]').size,1);
  assert.equal(row.querySelector('[data-column="sourceRecord.sourceStatus"] input'),null);
  const qty=row.querySelector('[data-execution-field=sampleQuantity]');qty.value='0';qty.dispatchEvent(new p.w.Event('input'));qty.focus();p.w.QcInspectionSheet.render();assert.equal(p.d.activeElement.dataset.executionField,'sampleQuantity');assert.equal(p.d.activeElement.value,'0');
  await p.w.QcInspectionSheet.flush();const sent=p.calls.find(c=>c.url.endsWith('/save')).body;assert.deepEqual(sent.inspectionExecution,{sampleQuantity:'0'});assert.equal(sent.remark,'原备注');
  await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-execution-field=sampleQuantity]').value,'0');
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelector('[data-execution-field]'),null);assert.equal(p.d.querySelector('[data-detail=defects]'),null);
 }finally{p.dom.window.close();}
});
test('structured details add/remove/save and cancel keep their own row and revision queue',async()=>{
 const p=await page();try{
  p.rows[0].inspectionExecution={defects:[{desc:'原不良',qty:'0',level:'',remark:''}],measurements:[{item:'原项目',standard:'',values:'',result:'',remark:''}]};await p.w.QcInspectionSheet.loadReview('pending');
  p.d.querySelector('[data-entry=a] [data-detail=defects]').click();
  const set=(k,value)=>{const n=p.d.querySelector('[data-detail-row="0"][data-detail-key="'+k+'"]');n.value=value;n.dispatchEvent(new p.w.Event('input'));};
  set('desc','包装压痕');set('qty','2');set('level','MIN 2.5');set('remark','测试明细');
  p.d.querySelector('[data-detail-add]').click();p.d.querySelector('[data-detail-remove="1"]').click();assert.equal(p.d.querySelectorAll('[data-detail-remove]').length,1);
  p.d.querySelector('[data-detail-save]').click();await tick();await tick();assert.equal(p.d.querySelector('dialog'),null);
  assert.equal(p.rows[0].inspectionExecution.defects[0].qty,'2');assert.equal(p.rows[1].inspectionExecution,undefined);
  await p.w.QcInspectionSheet.loadReview('pending');p.d.querySelector('[data-entry=a] [data-detail=defects]').click();assert.equal(p.d.querySelector('[data-detail-key=desc]').value,'包装压痕');
  p.d.querySelector('[data-detail-remove]').click();p.d.querySelector('[data-close]').click();assert.equal(p.rows[0].inspectionExecution.defects.length,1);
  p.d.querySelector('[data-entry=a] [data-detail=defects]').click();p.d.querySelector('[data-detail-remove]').click();p.d.querySelector('[data-detail-save]').click();await tick();await tick();assert.equal(p.rows[0].inspectionExecution.defects.length,0);
  assert.equal(p.d.querySelector('[data-entry=a] [data-detail=defects]'),null);p.d.querySelector('[data-entry=a] [data-detail=measurements]').click();set('item','长度');set('standard','100±1 mm');set('values','100.2 mm');set('result','PASS');set('remark','测量备注');p.d.querySelector('[data-detail-save]').click();await tick();await tick();assert.equal(p.rows[0].inspectionExecution.measurements[0].values,'100.2 mm');
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
test('protected source and historical fields are readonly and absent from every review save',async()=>{
 const p=await page();try{
  Object.assign(p.rows[0],{customerRequirements:'历史客户要求',customerCode:'旧补录编码',shipDate:'2026-12-20',shippedQuantity:'9',sourceRecord:{customerCode:'0007',shipDate:'2026-11-20',shippedQuantity:0},inspectionExecution:{reportMissingReason:'待补原件',resultExplanation:'历史解释'}});
  const before=structuredClone(p.rows[0]);await p.w.QcInspectionSheet.loadReview('pending');
  for(const key of ['customerRequirements','customerCode','shipDate','shippedQuantity'])assert.equal(p.d.querySelector('[data-review-field='+key+']'),null);
  for(const key of ['reportMissingReason','resultExplanation'])assert.equal(p.d.querySelector('[data-execution-field='+key+']'),null);
  assert.equal(p.d.querySelector('[data-review-info]'),null);assert.ok(p.d.querySelector('[data-audit=a]'));
  p.w.QcInspectionSheet.edit('a','remark','只修改备注');await p.w.QcInspectionSheet.flush();
  const save=p.calls.filter(c=>c.url.endsWith('/save')).at(-1).body;
  for(const key of ['customerRequirements','customerCode','shipDate','shippedQuantity','sourceRecord','inspectionExecution'])assert.equal(key in save,false,key);
  for(const key of ['customerRequirements','customerCode','shipDate','shippedQuantity','sourceRecord','inspectionExecution'])assert.deepEqual(p.rows[0][key],before[key]);
  assert.equal(p.d.querySelector('[data-entry=b] [data-review-info]'),null);
 }finally{p.dom.window.close();}
});
test('cancelled sources never show a return-to-workbench action',async()=>{
 const p=await page();try{p.rows[0].sourceCancelled=true;await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-return=a]'),null);assert.ok(p.d.querySelector('[data-return=b]'));}finally{p.dom.window.close();}
});

test('contract supplement retains leading zeroes and clearing while source quantities stay readonly',async()=>{
 const p=await page();try{
  p.rows[0].contractNo='SOURCE-01';p.rows[0].sourceRecord={contractNo:'SOURCE-01',customerCode:'0007',shippedQuantity:0};
  await p.w.QcInspectionSheet.loadReview('pending');const input=p.d.querySelector('[data-entry=a] [data-review-field=contractNo]');assert.equal(input.size,1);input.value='001-CONTRACT';input.dispatchEvent(new p.w.Event('input'));
  await p.w.QcInspectionSheet.flush();await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-review-field=contractNo]').value,'001-CONTRACT');assert.deepEqual(p.rows[0].sourceRecord,{contractNo:'SOURCE-01',customerCode:'0007',shippedQuantity:0});
  assert.equal(p.d.querySelector('[data-review-info]'),null);assert.equal(p.rows[0].sourceRecord.shippedQuantity,0);
  p.w.QcInspectionSheet.edit('a','contractNo','');await p.w.QcInspectionSheet.flush();await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-review-field=contractNo]').value,'');
  p.rows[0].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');assert.equal(p.d.querySelector('[data-review-field=contractNo]'),null);
 }finally{p.dom.window.close();}
});

test('order supplement audit uses business labels and keeps before and after values',async()=>{
 const p=await page();try{
  p.w.fetch=async()=>({ok:true,json:async()=>({items:[{id:1,action:'save',at:'2026-11-03T01:00:00Z',actor:{name:'测试用户'},location:'审核中心 · 待审核',changes:{contractNo:{before:'SRC',after:'001'},customerCode:{before:'0007',after:'00042'},shippedQuantity:{before:'12.5',after:'0'}}}]})});
  await p.w.QcInspectionAudit.show('a');const history=p.d.querySelector('.qia-event').textContent;
  assert.match(history,/合同号：SRC → 001/);assert.match(history,/客户编码：0007 → 00042/);assert.match(history,/已出货数量：12.5 → 0/);
 }finally{p.dom.window.close();}
});

test('report status uses observed choices, preserves legacy text and never derives from PASS',async()=>{
 const p=await page();try{
  let input=p.d.querySelector('[data-entry=a] [data-review-field=reportStatus]');assert.equal(input.tagName,'SELECT');assert.equal(input.value,'');assert.deepEqual([...input.options].map(o=>o.value),['','有']);
  p.rows[0].reportStatus='客户待签收';await p.w.QcInspectionSheet.loadReview('pending');input=p.d.querySelector('[data-entry=a] [data-review-field=reportStatus]');assert.equal(input.value,'客户待签收');assert.deepEqual([...input.options].map(o=>o.value),['','有','客户待签收']);
  input.value='有';input.dispatchEvent(new p.w.Event('change'));await p.w.QcInspectionSheet.flush();assert.equal(p.rows[0].reportStatus,'有');assert.equal(p.rows[1].reportStatus,undefined);
  await p.w.QcInspectionSheet.loadReview('pending');input=p.d.querySelector('[data-entry=a] [data-review-field=reportStatus]');input.value='';input.dispatchEvent(new p.w.Event('change'));await p.w.QcInspectionSheet.flush();assert.equal(p.rows[0].reportStatus,'');
 }finally{p.dom.window.close();}
});

test('detail entrances count valid business rows, disappear after empty save, and readonly approval stays readonly',async()=>{
 const p=await page();try{
  p.rows[0].inspectionExecution={defects:[null,{}, {desc:'  '},{id:'technical'}],measurements:[]};
  p.rows[1].inspectionExecution={defects:[{desc:'真实缺陷',qty:'0',level:'',remark:''}],measurements:[{item:'厚度',standard:'',values:'0',result:'PASS',remark:''}]};
  await p.w.QcInspectionSheet.loadReview('pending');assert.equal(p.d.querySelector('[data-entry=a] [data-detail]'),null);assert.equal(p.d.querySelector('[data-entry=c] [data-detail]'),null);assert.match(p.d.querySelector('[data-entry=b] [data-detail=defects]').textContent,/（1）/);
  p.rows[1].reviewState='approved';await p.w.QcInspectionSheet.loadReview('approved');p.d.querySelector('[data-detail=measurements]').click();assert.equal(p.d.querySelector('[data-detail-save]'),null);assert.equal(p.d.querySelector('[data-detail-key=values]').value,'0');assert.ok(p.d.querySelector('[data-detail-key=values]').disabled);
 }finally{p.dom.window.close();}
});

test('review has one transient success message; failure and conflict remain visible after its timer',async()=>{
 const p=await page();try{
  const label=()=>p.d.querySelector('[data-save-status=a]');assert.equal(label().textContent,'');assert.equal(p.d.querySelector('[data-review-status]'),null);
  const timers=[];const realTimeout=p.w.setTimeout.bind(p.w);p.w.setTimeout=(fn,ms)=>ms===2000?(timers.push(fn),999999):realTimeout(fn,ms);
  let release;const fetch=p.w.fetch;p.w.fetch=async(url,opts)=>url.endsWith('/save')?new Promise(resolve=>{release=()=>fetch(url,opts).then(resolve);}):fetch(url,opts);
  p.w.QcInspectionSheet.edit('a','remark','正在保存',true);assert.match(label().textContent,/保存中/);release();await p.w.QcInspectionSheet.flush();assert.equal(label().textContent,'已保存');timers.pop()();assert.equal(label().textContent,'');assert.ok(label().hidden);
  p.w.fetch=async(url,opts)=>url.endsWith('/save')?{ok:false,status:409,json:async()=>({detail:'记录已更新，请核对版本'})}:fetch(url,opts);
  p.w.QcInspectionSheet.edit('a','remark','冲突输入',true);await tick();assert.match(label().textContent,/保存失败.*记录已更新/);assert.equal(p.d.querySelector('[data-retry=a]').textContent,'核对版本并重试');assert.equal(p.w.QcInspectionSheet.model.drafts.get('a').remark,'冲突输入');
  for(const callback of timers)callback();assert.match(label().textContent,/保存失败/);assert.equal(label().hidden,false);
 }finally{p.dom.window.close();}
});

for(const state of ['approved','returned_to_inspection'])test('stale review '+state+' keeps cancelled input and releases only the explicitly discarded row without retrying a locked save',async()=>{
 const p=await page();try{
  const fetch=p.w.fetch;p.w.fetch=async(url,opts)=>url.endsWith('/save')?{ok:false,status:409,json:async()=>({detail:'只有待审核记录可编辑，请刷新核对状态'})}:fetch(url,opts);
  p.rows[0].reviewState=state;p.rows[0].revision++;p.rows[0].inspectionExecution={actualDate:'2026-11-06'};
  const date=p.d.querySelector('[data-entry=a] [data-execution-field=actualDate]');date.value='2026-11-15';date.dispatchEvent(new p.w.Event('input'));await p.w.QcInspectionSheet.pump('a');
  const draft=p.w.QcInspectionSheet.model.drafts.get('a');assert.equal(draft.conflict,true);
  let prompt='';p.w.confirm=text=>{prompt=text;return false;};await p.w.QcInspectionSheet.retry('a');
  assert.match(prompt,/实际验货日期.*2026-11-15/);assert.equal(p.w.QcInspectionSheet.model.drafts.get('a'),draft);assert.equal(p.w.QcInspectionSheet.navigationState().dirty,true);
  const other=p.w.QcInspectionSheet.model.drafts.get('b');other.dirty=true;other.error='其他行网络失败';other.remark='其他行输入';
  const writes=p.calls.filter(c=>c.body).length;p.w.confirm=()=>true;await p.w.QcInspectionSheet.retry('a');
  assert.equal(p.calls.filter(c=>c.body).length,writes);assert.equal(p.d.querySelector('[data-entry=a]'),null);assert.equal(p.w.QcInspectionSheet.model.drafts.has('a'),false);
  assert.equal(other.remark,'其他行输入');assert.equal(other.error,'其他行网络失败');assert.equal(p.w.QcInspectionSheet.navigationState().dirty,true);
  other.dirty=false;other.error='';assert.equal(p.w.QcInspectionSheet.navigationState().dirty,false);
  assert.equal(p.rows[0].reviewState,state);assert.equal(p.rows[0].inspectionExecution.actualDate,'2026-11-06');
 }finally{p.dom.window.close();}
});

test('module navigation offers an actionable state-conflict choice instead of an endless toast',async()=>{
 const p=await page();try{
  const app=fs.readFileSync(path.join(__dirname,'app.js'),'utf8'),start=app.indexOf('function showPage(');p.w.eval(app.slice(start,app.indexOf('\nfunction ',start+1)));
  p.rows[0].reviewState='approved';p.rows[0].revision++;
  const d=p.w.QcInspectionSheet.model.drafts.get('a');d.dirty=true;d.error='只有待审核记录可编辑';d.conflict=true;d.remark='需保留的未保存输入';
  let prompts=0;p.w.confirm=text=>{prompts++;assert.match(text,/已审核/);assert.match(text,/需保留的未保存输入/);return false;};
  p.w.showPage('records');await tick();assert.equal(prompts,1);assert.equal(d.remark,'需保留的未保存输入');assert.equal(p.w.QcInspectionSheet.navigationState().dirty,true);
  p.w.confirm=()=>true;p.w.showPage('records');await tick();assert.equal(p.w.QcInspectionSheet.navigationState().dirty,false);assert.equal(p.rows[0].reviewState,'approved');
 }finally{p.dom.window.close();}
});
