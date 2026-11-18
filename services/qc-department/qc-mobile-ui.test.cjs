const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM,VirtualConsole}=require('../../node_modules/jsdom');
const wait=ms=>new Promise(r=>setTimeout(r,ms||40));
test('live phone starts from server, switches fields with focus, saves locally and returns without submitting',async()=>{
 const folder=__dirname+'/mobile-inspection/',errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM(fs.readFileSync(folder+'index.html','utf8'),{runScripts:'outside-only',url:'http://mobile/api/qc-mobile/app/',pretendToBeVisual:true,virtualConsole:vc});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id),q=s=>d.querySelector(s),saved=new Map();
 w.HTMLElement.prototype.scrollIntoView=()=>{};w.HTMLElement.prototype.scrollTo=()=>{};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 w.URL.createObjectURL=()=> 'blob:preview';w.URL.revokeObjectURL=()=>{};
 w.indexedDB={open(){const request={};queueMicrotask(()=>{request.result={close(){},transaction(name,mode){const tx={objectStore:()=>({getAll(){const r={result:[...saved.values()]};queueMicrotask(()=>r.onsuccess());return r;},get(id){const r={result:saved.get(id)};queueMicrotask(()=>r.onsuccess());return r;},put(row){saved.set(row.id,{...row});}})};if(mode==='readwrite')setTimeout(()=>tx.oncomplete(),0);return tx;}};request.onsuccess();});return request;}};
 let row={id:'real-entry',customer:'隔离客户',poNo:'PO-001',productNo:'SKU-1',productName:'测试产品',dateFrom:'2026-11-17',result:'',inspectionProblem:'',remark:'',improvement:'审核保留内容',inspectionExecution:{sampleQuantity:'',inspectorId:''},revision:0,photos:[]};
 const writes=[];
 w.fetch=async(url,options={})=>{let result;
  if(url.endsWith('/context'))result={factory:'huaxing',actor:{id:'qc',name:'验货员'},scope:'one'};
  else if(url.endsWith('/options'))result={inspectors:[{id:'qc',name:'验货员'}]};
  else if(options.body){const body=JSON.parse(options.body);writes.push(url);assert.equal(body.revision,row.revision);if(url.endsWith('/save'))row={...row,...body,inspectionExecution:{...row.inspectionExecution,...body.inspectionExecution}};if(url.endsWith('/submit'))row={...row,submittedAt:'2026-11-17T00:00:00Z',reviewState:'pending'};row.revision++;result=row;}
  else result=url.endsWith('/entries')?{items:row.submittedAt?[]:[row]}:row;
  return {ok:true,json:async()=>JSON.parse(JSON.stringify(result))};};
 try{
  w.eval(fs.readFileSync(folder+'remote.js','utf8'));w.eval(fs.readFileSync(folder+'app.js','utf8'));await wait(100);
  assert.equal(d.querySelectorAll('#task-list .task').length,1);q('[data-task]').click();await wait();
  q('[data-result=PASS]').click();await wait();assert.equal(row.result,'PASS');
  const group=$('record-group');
  assert.deepEqual([...group.querySelectorAll('[data-note]')].map(note=>note.dataset.note),['problem','remark']);
  for (const [key,value] of [['problem','外箱压痕'],['remark','备注']]) {
    const note=q('[data-note="'+key+'"]');
    note.focus();
    assert.equal(d.activeElement,note);
    const parent=note.parentElement;
    note.dispatchEvent(new w.Event('compositionstart'));
    note.value='wai';note.dispatchEvent(new w.Event('input'));
    note.value=value;note.dispatchEvent(new w.Event('compositionend'));
    note.blur();
    assert.equal(note.parentElement,parent);
    assert.equal(group.contains(note),true);
    assert.equal($('composer').hidden,true);
  }
  await wait(750);
  assert.equal(row.inspectionProblem,'外箱压痕');assert.equal(row.improvement,'审核保留内容');assert.equal(row.remark,'备注');
  $('inspector').value='手填验货员';$('inspector').dispatchEvent(new w.Event('input'));await wait(600);assert.equal(row.inspectionExecution.inspector,'手填验货员');
  assert.equal($('save-return').disabled,false);$('save-return').click();await wait(150);
  assert.equal(row.submittedAt,undefined);assert.equal(d.querySelectorAll('#task-list .task').length,1);assert.equal($('tasks').hidden,false);assert.equal($('list-notice').textContent,'');assert.match(q('.task-sync').textContent,/已同步/);
  assert.equal(writes.some(url=>url.endsWith('/submit')),false);assert.equal(saved.get('real-entry').remark,'备注');assert.equal(errors.length,0,errors.join('\n'));
 }finally{dom.window.close();}
});
test('desktop entry is immediately left of unified submit and cannot mutate records',async()=>{
 const dom=new JSDOM('<div id="page-records"><div class="qis-submit-actions"><button id="qis-record-batch">提交审核</button></div></div>',{runScripts:'outside-only'}),w=dom.window,d=w.document;
 w.__QC_NEXUS={factory:'huaxing',workflow:{edit:true}};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};let expired=false;w.fetch=async()=>({ok:true,json:async()=>({qr:'data:image/png;base64,AA==',actor:'验货员',factory:'huaxing',expiresAt:Date.now()/1000+(expired?-1:300)})});
 try{
  w.eval(fs.readFileSync(__dirname+'/qc-mobile-entry.js','utf8'));const entry=d.getElementById('qc-mobile-entry');assert.equal(d.getElementById('qis-record-batch').previousElementSibling,entry);entry.click();await wait();
  let dialog=d.querySelector('dialog');assert(dialog.open);assert.equal(dialog.querySelector('img').hidden,false);assert.equal(dialog.querySelector('header,footer,[data-close]'),null);assert.equal(dialog.querySelector('.qc-mobile-pair-state').hidden,true);
  dialog.getBoundingClientRect=()=>({left:100,top:100,right:388,bottom:388});
  const pointer=(type,x,y)=>dialog.dispatchEvent(new w.MouseEvent(type,{bubbles:true,clientX:x,clientY:y}));
  pointer('pointerdown',200,200);pointer('click',200,200);assert(dialog.isConnected,'QR click must keep it open');
  pointer('pointerdown',20,20);pointer('click',20,20);assert.equal(d.querySelector('dialog'),null);assert.equal(d.activeElement,entry);
  expired=true;entry.click();await wait();dialog=d.querySelector('dialog');assert.equal(dialog.querySelector('img').hidden,true);assert.equal(dialog.querySelector('[data-refresh]').hidden,false);assert.match(dialog.textContent,/已过期/);
  expired=false;dialog.querySelector('[data-refresh]').click();await wait();assert.equal(dialog.querySelector('img').hidden,false);assert.equal(dialog.querySelector('.qc-mobile-pair-state').hidden,true);
 }finally{dom.window.close();}
});
