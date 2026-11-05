'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const project=process.env.QC_TEST_PROJECT||path.resolve(__dirname,'../..');
const {JSDOM}=require(path.join(project,'node_modules/jsdom'));
const sourceRoot=process.env.QC_TEST_SOURCE||project;
const html=fs.readFileSync(path.join(sourceRoot,'services/qc-department/index.html'),'utf8');
const script=fs.readFileSync(path.join(sourceRoot,'services/qc-department/qc-inspection-sheet.js'),'utf8');
const columns=['date','customer','poNo','country','productNo','productName','quantity','unitsPerCarton','cartonCount','production','agency','customerPo','completion','result','remark','photos'].map((key,index)=>({key,label:['日期','客户','PO#','出口国','货号','产品名称','数量','装箱','箱数','生产','机构','客PO#','完成情况','验货结果','备注','照片'][index]}));
const copy=x=>JSON.parse(JSON.stringify(x)),tick=()=>new Promise(resolve=>setTimeout(resolve,5));
async function page(){
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/api/qc-department/huaxing/u-test/'}),w=dom.window,calls=[];
 let rows=['a','b','c'].map((id,i)=>({id,sourceKey:'source:'+id,customer:'客户中文',poNo:'0000'+i,productNo:'0001',productName:'同款产品',result:'',remark:'',photos:[],revision:0,dateFrom:'2026-10-29',dateTo:'2026-10-29',updatedAt:'',quantity:10}));
 let fail=false,delay=0,active=0,maxActive=0,bookVersion=0,undo=false;
 w.__QC_NEXUS={exportAllowed:true,workflow:{edit:true}};w.confirm=()=>true;w.showToast=(msg)=>calls.push({toast:msg});
 w.HTMLAnchorElement.prototype.click=function() {calls.push({download:this.href});};
 w.URL.createObjectURL=()=> 'blob:test';w.URL.revokeObjectURL=()=>{};
 w.fetch=async(url,options={})=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({url,body});
  if(url.endsWith('/entries'))return {ok:true,json:async()=>({items:copy(rows),columns})};
  if(fail)return {ok:false,status:503,json:async()=>({detail:'网络断开，未保存'})};
  if(url.includes('/workbook/status'))return {ok:true,json:async()=>({version:bookVersion,undoAvailable:undo,count:rows.length,excluded:0,revisions:Object.fromEntries(rows.map(r=>[r.id,r.revision])),scope:{dateFrom:'2026-10-26',dateTo:'2026-11-01'}})};
  if(url.endsWith('/workbook/download'))return {ok:true,blob:async()=>new w.Blob(['saved-workbook'])};
  if(url.endsWith('/workbook/import')||url.endsWith('/workbook/undo')||url.endsWith('/workbook/replace')){assert.equal(body.expectedVersion,bookVersion);bookVersion++;undo=url.endsWith('/import');return {ok:true,json:async()=>({version:bookVersion,undoAvailable:undo,status:url.endsWith('/replace')?'replaced':undo?'imported':'undone',count:rows.length})};}
  if(url.endsWith('/photos')&&body.name==='corrupt.jpg')return {ok:false,status:422,json:async()=>({detail:'图片损坏或格式不支持'})};
  if(url.endsWith('/export'))return {ok:true,json:async()=>({url:'api/inspection-sheet/exports/'+'a'.repeat(32),filename:'test.xlsx'})};
  const id=url.split('/').at(-2),row=rows.find(r=>r.id===id);
  assert.ok(row,'stable entry identity');active++;maxActive=Math.max(maxActive,active);
  if(delay)await new Promise(resolve=>setTimeout(resolve,delay));
  const onlyInitialPhotos=url.includes('/workbook/entries/')&&body.revision+row.photos.length===row.revision&&row.result===''&&row.remark==='';
  if(!onlyInitialPhotos)assert.equal(body.revision,row.revision,'serialized requests use latest revision');
  if(url.endsWith('/save')){Object.assign(row,{result:body.result,remark:body.remark});if(body.inspectionExecution){row.inspectionExecution={...row.inspectionExecution,...body.inspectionExecution};row.actualDate=row.inspectionExecution.actualDate;}}
  if(url.endsWith('/photos'))row.photos.push({id:'photo-'+row.photos.length,name:body.name});
  if(url.endsWith('/remove-photo'))row.photos=row.photos.filter(p=>p.id!==body.photoId);
  row.revision++;active--;
  return {ok:true,json:async()=>copy(row)};
 };
 w.eval(fs.readFileSync(path.join(sourceRoot,'services/qc-department/qc-inspection-audit.js'),'utf8'));w.eval(fs.readFileSync(path.join(sourceRoot,'services/qc-department/qc-photo-paste.js'),'utf8'));w.eval(script);await tick();if(!w.QcInspectionSheet.model.loaded)await w.QcInspectionSheet.load();
 return {dom,w,d:w.document,calls,get rows(){return rows;},set fail(value){fail=value;},set delay(value){delay=value;},get maxActive(){return maxActive;}};
}
test('18 display columns including optional actual date, inline four-result controls, reused remarks, real camera/file inputs and no drawer',async()=>{
 const p=await page();try{
  assert.equal(p.d.querySelectorAll('.qis-table thead th').length,18);
  assert.deepEqual([...p.d.querySelector('[data-result]').options].map(x=>x.value),['','PASS','FAIL','PENDING','LG']);
  assert.equal(p.d.querySelector('[data-result] option[value=""]').disabled,false);
  assert.equal(p.d.querySelector('[data-result]').value,'');assert.equal(p.d.querySelectorAll('[data-remark]').length,3);
  assert.equal(p.d.querySelector('[data-camera]').getAttribute('capture'),'environment');assert.ok(p.d.querySelector('[data-files]').multiple);
  assert.equal(p.d.querySelector('.qwf-dialog'),null);assert.ok(p.d.getElementById('page-review'));
 }finally{p.dom.window.close();}
});
test('rapid PASS to FAIL and long bilingual remarks save in order, reload and other rows stay independent',async()=>{
 const p=await page();try{
  p.delay=20;p.w.QcInspectionSheet.edit('a','result','PASS',true);
  p.w.QcInspectionSheet.edit('a','result','FAIL',true);p.w.QcInspectionSheet.edit('a','remark','中文 English 0123 !\n'.repeat(100));
  await p.w.QcInspectionSheet.flush();assert.equal(p.maxActive,1);
  assert.equal(p.rows[0].result,'FAIL');assert.equal(p.rows[1].result,'');
  await p.w.QcInspectionSheet.load();assert.equal(p.d.querySelector('[data-result="a"]').value,'FAIL');
  assert.equal(p.d.querySelector('[data-remark="a"]').value,'中文 English 0123 !\n'.repeat(100));
  assert.match(p.d.querySelector('[data-save-status="a"]').textContent,/已保存/);
 }finally{p.dom.window.close();}
});
test('failed saves keep draft through filtering, block refresh/export and can retry without loss',async()=>{
 const p=await page();try{
  p.fail=true;p.w.QcInspectionSheet.edit('a','remark','不能丢失的现场备注',true);await tick();
  assert.match(p.d.querySelector('[data-save-status="a"]').textContent,/保存失败/);
  await p.w.QcInspectionSheet.load();assert.equal(p.w.QcInspectionSheet.model.drafts.get('a').remark,'不能丢失的现场备注');
  p.d.getElementById('searchInput').value='00001';p.w.QcInspectionSheet.render();assert.equal(p.d.querySelectorAll('[data-entry]').length,1);
  p.d.getElementById('searchInput').value='';p.w.QcInspectionSheet.render();assert.equal(p.d.querySelector('[data-remark="a"]').value,'不能丢失的现场备注');
  await p.w.QcInspectionSheet.exportExcel();assert.ok(!p.calls.some(c=>c.url?.endsWith('/export')));
  p.fail=false;await p.w.QcInspectionSheet.retry('a');assert.equal(p.rows[0].remark,'不能丢失的现场备注');
 }finally{p.dom.window.close();}
});
test('photo upload failure is visible, retry persists multiple photos on the same task, remove and export',async()=>{
 const p=await page();try{
  const control=p.d.querySelector('[data-files="b"]');
  Object.defineProperty(control,'files',{value:[new p.w.File(['image1'],'照片一.png',{type:'image/png'}),new p.w.File(['image2'],'照片二.png',{type:'image/png'})]});
  p.fail=true;await p.w.QcInspectionSheet.upload('b',control);assert.equal(p.rows[1].photos.length,0);
  assert.match(p.d.querySelector('[data-save-status="b"]').textContent,/保存失败/);
  p.fail=false;await p.w.QcInspectionSheet.retry('b');assert.equal(p.rows[1].photos.length,2);assert.equal(p.rows[0].photos.length,0);
  await p.w.QcInspectionSheet.load();assert.equal(p.d.querySelectorAll('[data-photo-list="b"] img').length,2);
  p.w.confirm=()=>false;p.d.querySelector('[data-entry="b"] [data-remove-photo]').click();await tick();assert.equal(p.rows[1].photos.length,2);
  p.w.confirm=()=>true;
  p.d.querySelector('[data-entry="b"] [data-remove-photo]').click();await tick();assert.equal(p.rows[1].photos.length,1);
  await p.w.QcInspectionSheet.flush();await p.w.QcInspectionSheet.exportExcel();
  assert.ok(p.calls.some(c=>c.url?.endsWith('/workbook/download')));assert.ok(!p.calls.some(c=>c.url?.endsWith('/workbook/import')));assert.ok(p.calls.some(c=>c.download));
 }finally{p.dom.window.close();}
});
test('import flushes all records and current filters without confirmation; undo has one guarded version',async()=>{
 const p=await page();try{
  p.w.confirm=()=>{throw Error('import must not ask confirmation');};
  p.w.QcInspectionSheet.edit('a','remark','先保存再导入');p.d.getElementById('searchInput').value='00000';
  await p.w.QcInspectionSheet.changeWorkbook('import');
  const call=p.calls.find(c=>c.url?.endsWith('/workbook/import'));assert.ok(call);assert.equal(call.body.revisions.a,p.rows[0].revision);assert.equal(Object.keys(call.body.revisions).length,3);
  assert.equal(call.body.scope.search,'00000');assert.equal(p.rows[0].remark,'先保存再导入');assert.equal(p.w.QcInspectionSheet.workbook.state.undoAvailable,true);
  await p.w.QcInspectionSheet.changeWorkbook('undo');const undo=p.calls.find(c=>c.url?.endsWith('/workbook/undo'));assert.equal(undo.body.expectedVersion,1);assert.equal(p.rows[0].remark,'先保存再导入');assert.equal(p.w.QcInspectionSheet.workbook.state.undoAvailable,false);
 }finally{p.dom.window.close();}
});
test('export reads persisted workbook without flushing a new edit or silently importing it',async()=>{
 const p=await page();try{
  p.w.QcInspectionSheet.edit('a','remark','尚未导入');await p.w.QcInspectionSheet.exportExcel();
  assert.equal(p.rows[0].remark,'');assert.ok(p.calls.some(c=>c.download));assert.ok(!p.calls.some(c=>c.url?.endsWith('/workbook/import')));
 }finally{p.dom.window.close();}
});
test('mixed oversized photo selection cannot silently upload a subset or report success',async()=>{
 const p=await page();try{
  const control=p.d.querySelector('[data-files="a"]');
  Object.defineProperty(control,'files',{value:[new p.w.File(['ok'],'正常.png'),{name:'过大.jpg',size:11*1024*1024}]});
  await p.w.QcInspectionSheet.upload('a',control);
  assert.equal(p.rows[0].photos.length,0);assert.equal(p.w.QcInspectionSheet.model.drafts.get('a').queue.length,0);
  assert.match(p.d.querySelector('[data-save-status="a"]').textContent,/过大.jpg/);
  await p.w.QcInspectionSheet.exportExcel();assert.ok(!p.calls.some(c=>c.url?.endsWith('/export')));
  assert.equal(p.d.querySelector('[data-retry="a"]').textContent,'清除失败选择');
  await p.w.QcInspectionSheet.retry('a');assert.equal(p.w.QcInspectionSheet.navigationState().dirty,false);
 }finally{p.dom.window.close();}
});
test('discarding a rejected photo preserves saved photos, queued good files and unsaved notes',async()=>{
 const p=await page();try{
  const control=p.d.querySelector('[data-files="b"]');
  Object.defineProperty(control,'files',{configurable:true,value:[new p.w.File(['saved'],'saved.jpg')]});
  await p.w.QcInspectionSheet.upload('b',control);
  Object.defineProperty(control,'files',{value:[new p.w.File(['bad'],'corrupt.jpg'),new p.w.File(['good'],'good.jpg')]});
  await p.w.QcInspectionSheet.upload('b',control);
  assert.match(p.d.querySelector('[data-save-status="b"]').textContent,/corrupt.jpg.*图片损坏/);
  assert.equal(p.d.querySelector('[data-retry="b"]').textContent,'清除失败照片');
  assert.equal(p.rows[1].photos.length,1);
  p.w.QcInspectionSheet.edit('b','remark','失败时保留的备注');
  await p.w.QcInspectionSheet.retry('b');
  assert.deepEqual(p.rows[1].photos.map(photo=>photo.name),['saved.jpg','good.jpg']);
  assert.equal(p.rows[1].remark,'失败时保留的备注');assert.equal(p.rows[0].photos.length,0);
  assert.equal(p.w.QcInspectionSheet.navigationState().dirty,false);
 }finally{p.dom.window.close();}
});

test('failed photo queue is preserved while mapped text imports without photo retries',async()=>{
 const p=await page();try{
  const control=p.d.querySelector('[data-files="b"]');
  Object.defineProperty(control,'files',{value:[new p.w.File(['bad'],'corrupt.jpg'),new p.w.File(['good'],'good.jpg')]});
  await p.w.QcInspectionSheet.upload('b',control);
  const before=p.calls.filter(c=>c.url?.endsWith('/photos')).length;
  p.w.QcInspectionSheet.edit('b','remark','拉杆松，客户要求周五补验');
  await p.w.QcInspectionSheet.changeWorkbook('import');
  assert.ok(p.calls.some(c=>c.url?.endsWith('/workbook/import')));
  assert.equal(p.rows[1].remark,'拉杆松，客户要求周五补验');
  assert.equal(p.calls.filter(c=>c.url?.endsWith('/photos')).length,before);
  assert.equal(p.w.QcInspectionSheet.model.drafts.get('b').queue.length,2);
  assert.match(p.w.QcInspectionSheet.model.drafts.get('b').error,/图片损坏/);
 }finally{p.dom.window.close();}
});
test('photo reading and pending upload do not delay importing already saved text',async()=>{
 const p=await page();try{
  p.w.QcInspectionSheet.edit('a','remark','已保存');await p.w.QcInspectionSheet.flush();
  const d=p.w.QcInspectionSheet.model.drafts.get('a');d.reading=true;d.busy=true;d.busyKind='photo';
  await p.w.QcInspectionSheet.changeWorkbook('import');
  assert.ok(p.calls.some(c=>c.url?.endsWith('/workbook/import')));assert.equal(d.reading,true);assert.equal(d.busy,true);
 }finally{p.dom.window.close();}
});
test('actual download uses the authenticated persisted-file URL, with no Blob rewrite',async()=>{
 const p=await page();try{
  p.w.URL.createObjectURL=()=>{throw Error('must download server file directly');};
  await p.w.QcInspectionSheet.exportExcel();
  assert.match(p.calls.find(c=>c.download).download,/api\/inspection-sheet\/workbook\/download$/);
  assert.ok(!p.calls.some(c=>c.url?.endsWith('/save')||c.url?.endsWith('/workbook/import')));
 }finally{p.dom.window.close();}
});
test('unavailable historical photo warning stays visible while text remains editable',async()=>{
 const p=await page();try{
  p.rows[0].photoWarning='来源照片暂不可用；刷新重试';
  p.w.QcInspectionSheet.model.items[0].photoWarning=p.rows[0].photoWarning;p.w.QcInspectionSheet.render();
  assert.match(p.d.querySelector('[data-photo-list="a"]').textContent,/来源照片暂不可用/);
  p.w.QcInspectionSheet.edit('a','remark','仍可录入');await p.w.QcInspectionSheet.changeWorkbook('import');
  assert.equal(p.rows[0].remark,'仍可录入');assert.match(p.d.querySelector('[data-photo-list="a"]').textContent,/来源照片暂不可用/);
 }finally{p.dom.window.close();}
});
test('an upload queue already running resumes after the independent mapped save',async()=>{
 const p=await page();try{
  const original=p.w.fetch;let release;
  const held=new Promise(resolve=>{release=resolve;});
  p.w.fetch=async(url,options)=>{if(url.includes('/workbook/entries/'))await held;return original(url,options);};
  p.delay=15;const control=p.d.querySelector('[data-files="b"]');
  Object.defineProperty(control,'files',{value:[new p.w.File(['first'],'first.jpg'),new p.w.File(['second'],'second.jpg')]});
  const uploading=p.w.QcInspectionSheet.upload('b',control);
  for(let i=0;i<60&&p.w.QcInspectionSheet.model.drafts.get('b')?.busyKind!=='photo';i++)await tick();
  assert.equal(p.w.QcInspectionSheet.model.drafts.get('b').busyKind,'photo');
  p.w.QcInspectionSheet.edit('b','remark','文字保存与照片分开');
  const importing=p.w.QcInspectionSheet.changeWorkbook('import');
  for(let i=0;i<60&&p.rows[1].photos.length!==1;i++)await tick();
  assert.equal(p.rows[1].photos.length,1);release();await importing;await uploading;
  for(let i=0;i<60&&p.rows[1].photos.length!==2;i++)await tick();
  assert.equal(p.rows[1].photos.length,2);assert.equal(p.rows[1].remark,'文字保存与照片分开');
  assert.equal(p.w.QcInspectionSheet.model.drafts.get('b').queue.length,0);
 }finally{p.dom.window.close();}
});
test('PENDING persists independently and latest workbook upload uses selected bytes without changing records',async()=>{
 const p=await page();try{
  const q=p.w.QcInspectionSheet;
  q.edit('a','result','PENDING',true);await q.flush();await q.load();
  p.d.getElementById('filterResult').value='PENDING';q.render();assert.equal(q.filtered().length,1);
  assert.equal(p.d.querySelector('[data-result="a"]').value,'PENDING');
  assert.equal(p.d.getElementById('recordsSelectionHint').textContent,'');
  const previous=copy(p.rows);await q.bookStatus(true);
  await q.changeWorkbook('replace',new p.w.File(['binary-workbook'],'新年度.xlsx'));
  const request=p.calls.find(c=>c.url?.endsWith('/workbook/replace'));
  assert.equal(request.body.filename,'新年度.xlsx');assert.equal(Buffer.from(request.body.content,'base64').toString(),'binary-workbook');
  assert.deepEqual(p.rows,previous);assert.match(q.workbook.message,/旧工作簿已归档/);
  assert.equal(q.workbook.busy,false);assert.equal(p.d.getElementById('qisLatest').disabled,false);
 }finally{p.dom.window.close();}
});

test('dates keep their year and a filled result clears the historical blank warning',async()=>{
 const p=await page();try{
  const row=p.w.QcInspectionSheet.model.items[0];
  row.dateFrom='2025-12-30';row.dateTo='2026-01-03';row.historicalResult='COND';row.result='PASS';
  p.w.QcInspectionSheet.model.drafts.delete('a');p.w.QcInspectionSheet.render();
  assert.match(p.d.querySelector('[data-entry="a"] td[data-column="date"]').textContent,/2025-12-30 至 2026-01-03/);
  assert.equal(p.d.querySelector('[data-entry="a"] .qis-error'),null);
  row.dateTo='2025-12-30';row.result='';
  p.w.QcInspectionSheet.model.drafts.delete('a');p.w.QcInspectionSheet.render();
  assert.match(p.d.querySelector('[data-entry="a"] td[data-column="date"]').textContent,/2025年12月30日/);
  assert.match(p.d.querySelector('[data-entry="a"]').textContent,/原历史结论：COND/);
 }finally{p.dom.window.close();}
});
test('planned date default groups customers within each day, keeps missing dates last and modification sort independent',async()=>{
 const p=await page();try{
  assert.equal(p.d.getElementById('filterSort').value,'date-asc');
  const seed=p.w.QcInspectionSheet.model.items[0];
  const rows=[
   {id:'e',dateFrom:'2026-10-29',customer:'EDU',updatedAt:'6'},
   {id:'b',dateFrom:'2026-10-27',dateTo:'2026-10-29',customer:'Dickie',updatedAt:'5'},
   {id:'c',dateFrom:'2026-10-27',customer:'BUZZBEE',updatedAt:'4'},
   {id:'a',dateFrom:'2026-10-27',customer:'Dickie',updatedAt:'3'},
   {id:'d',dateFrom:'2026-10-28',customer:'EDU',updatedAt:'2'},
   {id:'z',dateFrom:'',customer:'BUZZBEE',updatedAt:'1'}
  ].map(row=>({...seed,...row}));
  p.w.QcInspectionSheet.model.items=rows;
  const ids=()=>Array.from(p.w.QcInspectionSheet.filtered(),r=>r.id);
  assert.deepEqual(ids(),['c','a','b','d','e','z']);
  p.d.getElementById('filterSort').value='date-desc';
  assert.deepEqual(ids(),['e','d','c','a','b','z']);
  p.d.getElementById('filterSort').value='mod-desc';
  assert.deepEqual(ids(),['e','b','c','a','d','z']);
  assert.deepEqual(rows.map(r=>r.id),['e','b','c','a','d','z']);
 }finally{p.dom.window.close();}
});


test('successful merge reloads pending rows while failed merge keeps them and export remains available',async()=>{
 const p=await page();try{
  const q=p.w.QcInspectionSheet,original=p.w.fetch;let merged=false;
  p.w.fetch=async(url,options)=>{
   const response=await original(url,options);
   if(url.endsWith('/workbook/import')&&response.ok)merged=true;
   if(url.endsWith('/entries')&&merged)return {ok:true,json:async()=>({items:[],columns})};
   return response;
  };
  p.fail=true;await q.changeWorkbook('import');
  assert.equal(q.model.items.length,3);assert.equal(merged,false);
  p.fail=false;await q.changeWorkbook('import');
  assert.equal(q.model.items.length,0);assert.equal(p.d.querySelectorAll('[data-entry]').length,0);
  assert.equal(p.d.getElementById('btnExportInspectionExcel').disabled,false);
  assert.equal(p.rows.length,3,'source data is retained');
  await q.load();assert.equal(q.model.items.length,0,'reload does not restore merged rows');
 }finally{p.dom.window.close();}
});
test('input events debounce independently and stable row selection survives rerender and sort',async()=>{
 const p=await page();try{
  const row=p.d.querySelector('[data-entry="b"]');row.click();assert.equal(p.d.querySelectorAll('.qis-selected').length,1);assert.equal(row.getAttribute('aria-selected'),'true');
  const input=row.querySelector('[data-remark]');input.focus();assert.equal(p.w.QcInspectionSheet.model.selectedId,'b');input.value='真实输入事件自动保存';input.dispatchEvent(new p.w.Event('input'));
  assert.equal(p.rows[1].remark,'');await new Promise(r=>setTimeout(r,720));assert.equal(p.rows[1].remark,'真实输入事件自动保存');
  p.w.QcInspectionSheet.render();assert.equal(p.d.querySelector('.qis-selected').dataset.entry,'b');
  p.d.getElementById('filterSort').value='date-desc';p.w.QcInspectionSheet.render();assert.equal(p.d.querySelector('.qis-selected').dataset.entry,'b');
  assert.deepEqual([...p.d.querySelectorAll('#recordsTableWrap thead th')].map(e=>e.dataset.column).slice(0,3),['date','customer','poNo']);
 }finally{p.dom.window.close();}
});
test('timed out autosave retains input and retry uses CAS without pretending success',async()=>{
 const p=await page();try{
  const fetch=p.w.fetch,timer=p.w.setTimeout.bind(p.w);
  p.w.setTimeout=(fn,ms,...args)=>timer(fn,ms===20000?5:ms,...args);
  p.w.fetch=(url,options={})=>url.endsWith('/save')?new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new p.w.DOMException('aborted','AbortError')))):fetch(url,options);
  p.w.QcInspectionSheet.edit('a','remark','超时保留输入',true);
  await new Promise(resolve=>setTimeout(resolve,25));
  assert.match(p.d.querySelector('[data-save-status="a"]').textContent,/保存失败.*请求超时/);
  assert.equal(p.rows[0].remark,'');assert.equal(p.w.QcInspectionSheet.model.drafts.get('a').remark,'超时保留输入');
  p.w.fetch=fetch;await p.w.QcInspectionSheet.retry('a');assert.equal(p.rows[0].remark,'超时保留输入');
 }finally{p.dom.window.close();}
});

test('empty result has contextual closable notification and focus, without submitting or dropping the row',async()=>{
 const p=await page();try{
  p.d.querySelector('[data-submit="a"]').click();await tick();
  const notice=p.d.querySelector('.qis-notice[role=alert]');assert.match(notice.textContent,/无法提交审核.*客户中文.*00000.*验货结果/s);
  assert.equal(p.calls.filter(c=>c.url?.endsWith('/submit')).length,0);assert.ok(p.d.querySelector('[data-entry=a]'));
  notice.querySelector('[data-locate]').click();assert.equal(p.d.activeElement.dataset.result,'a');
  notice.querySelector('button[aria-label="关闭提交失败通知"]').click();assert.equal(notice.dataset.noticeState,'closing');await new Promise(resolve=>setTimeout(resolve,150));assert.equal(p.d.querySelector('.qis-notice'),null);
 }finally{p.dom.window.close();}
});

test('backend rejection and failed save keep drafts and expose actual causes',async()=>{
 const p=await page();try{
  p.w.QcInspectionSheet.edit('a','result','PASS',true);await p.w.QcInspectionSheet.flush();
  const original=p.w.fetch;p.w.fetch=async(url,opts)=>url.endsWith('/submit')?{ok:false,status:409,json:async()=>({detail:'记录状态已变化，请刷新核对'})}:original(url,opts);
  p.d.querySelector('[data-submit=a]').click();await tick();assert.match(p.d.querySelector('.qis-notice').textContent,/记录状态已变化/);assert.ok(p.d.querySelector('[data-entry=a]'));
  p.fail=true;p.w.QcInspectionSheet.edit('a','remark','保留备注');p.d.querySelector('[data-submit=a]').click();await tick();await tick();
  assert.match(p.d.querySelector('.qis-notice').textContent,/网络断开，未保存/);assert.equal(p.w.QcInspectionSheet.model.drafts.get('a').remark,'保留备注');
 }finally{p.dom.window.close();}
});

test('network failure is explicit and rapid submit clicks create only one in-flight request',async()=>{
 const p=await page();try{
  p.w.QcInspectionSheet.edit('a','result','PASS',true);await p.w.QcInspectionSheet.flush();
  const original=p.w.fetch;let submissions=0,release;
  p.w.fetch=async(url,opts)=>{if(url.endsWith('/submit')){submissions++;await new Promise(r=>release=r);throw new p.w.TypeError('Failed to fetch');}return original(url,opts);};
  const button=p.d.querySelector('[data-submit=a]');button.click();button.click();await tick();assert.equal(submissions,1);release();await tick();
  assert.match(p.d.querySelector('.qis-notice').textContent,/网络连接异常/);assert.equal(button.disabled,false);assert.ok(p.d.querySelector('[data-entry=a]'));
 }finally{p.dom.window.close();}
});
function pasteEvent(p,target,files=[],items=null){const event=new p.w.Event('paste',{bubbles:true,cancelable:true});Object.defineProperty(event,'clipboardData',{value:{files,items:items||files.map(file=>({kind:'file',type:file.type,getAsFile:()=>file}))}});target.dispatchEvent(event);return event;}
test('native image paste follows the highlighted row, keeps burst order and survives reload',async()=>{
 const p=await page();try{
  p.d.getElementById('page-records').classList.add('active');const image=name=>new p.w.File([name],name,{type:'image/png'});
  assert.equal(pasteEvent(p,p.d.body,[image('unselected.png')]).defaultPrevented,false);assert.equal(p.calls.filter(c=>c.url?.endsWith('/photos')).length,0);
  const row=p.d.querySelector('[data-entry="b"]');row.click();
  assert.ok(pasteEvent(p,row,[image('first.png'),image('second.png')]).defaultPrevented);
  pasteEvent(p,row,[image('third.png')]);p.d.querySelector('[data-entry="c"]').click();pasteEvent(p,p.d.body,[image('other.png')]);
  assert.equal(p.w.QcInspectionSheet.navigationState().busy,true);await p.w.QcInspectionSheet.flush();
  assert.deepEqual(p.rows[1].photos.map(f=>f.name),['first.png','second.png','third.png']);assert.deepEqual(p.rows[2].photos.map(f=>f.name),['other.png']);assert.equal(p.rows[0].photos.length,0);
  await p.w.QcInspectionSheet.load();assert.equal(p.d.querySelectorAll('[data-photo-list="b"] img').length,3);
  const text=p.d.querySelector('[data-remark="b"]');assert.equal(pasteEvent(p,text).defaultPrevented,false);
 }finally{p.dom.window.close();}
});
test('paste ignores hidden rows, other pages, unrelated dialogs and image URLs; locked rows stay readonly',async()=>{
 const p=await page();try{
  const image=new p.w.File(['x'],'file.png',{type:'image/png'});p.d.getElementById('page-records').classList.add('active');p.d.querySelector('[data-entry="b"]').click();
  p.d.getElementById('searchInput').value='00000';p.w.QcInspectionSheet.render();pasteEvent(p,p.d.body,[image]);assert.equal(p.calls.filter(c=>c.url?.endsWith('/photos')).length,0);
  p.d.getElementById('searchInput').value='';p.w.QcInspectionSheet.render();p.d.querySelector('[data-entry="b"]').click();
  const dialog=p.d.createElement('dialog');dialog.open=true;p.d.body.append(dialog);assert.equal(pasteEvent(p,dialog,[image]).defaultPrevented,false);dialog.remove();
  p.d.getElementById('page-records').classList.remove('active');pasteEvent(p,p.d.body,[image]);p.d.getElementById('page-records').classList.add('active');
  pasteEvent(p,p.d.body,[],[{kind:'string',type:'text/html',getAsString:cb=>cb('<img src="https://example.com/private.png">')}]);
  p.w.QcInspectionSheet.model.items.find(r=>r.id==='b').submittedAt='2026-11-03T00:00:00Z';assert.ok(pasteEvent(p,p.d.body,[image]).defaultPrevented);await tick();
  assert.equal(p.calls.filter(c=>c.url?.endsWith('/photos')).length,0);
 }finally{p.dom.window.close();}
});
test('pasted upload failure retains the same retry job; fallback files and oversize validation reuse normal path',async()=>{
 const p=await page();try{
  p.d.getElementById('page-records').classList.add('active');const row=p.d.querySelector('[data-entry="a"]');row.click();const file=new p.w.File(['x'],'retry.png',{type:'image/png'});
  p.fail=true;pasteEvent(p,row,[file],[]);await assert.rejects(p.w.QcInspectionSheet.flush());const first=p.calls.find(c=>c.url?.endsWith('/photos'));
  p.fail=false;await p.w.QcInspectionSheet.retry('a');const sent=p.calls.filter(c=>c.url?.endsWith('/photos'));assert.equal(sent.length,2);assert.equal(sent[1].body.requestKey,first.body.requestKey);assert.equal(p.rows[0].photos.length,1);
  const big=new p.w.File(['x'],'oversize.png',{type:'image/png'});Object.defineProperty(big,'size',{value:11*1024*1024});pasteEvent(p,row,[big]);await assert.rejects(p.w.QcInspectionSheet.flush());assert.match(p.d.querySelector('[data-save-status="a"]').textContent,/10 MB/);assert.equal(p.calls.filter(c=>c.url?.endsWith('/photos')).length,2);
 }finally{p.dom.window.close();}
});


test('workbench date uses native editor, autosaves only its patch, reloads and clears without a planned-date prefill',async()=>{
 const p=await page();try{
  const input=()=>p.d.querySelector('[data-entry="a"] [data-execution-field="actualDate"]');
  assert.equal(input().type,'date');assert.equal(input().value,'');assert.match(input().title,/未填写时.*计划日期/);
  const order=[...p.d.querySelectorAll('th[data-column]')].map(n=>n.dataset.column);
  assert.deepEqual(order.slice(0,3),['date','customer','poNo']);assert.equal(order.at(-1),'actualDate');
  p.rows[0].inspectionExecution={actualDate:'',reportNo:'KEEP',sampleQuantity:'0'};
  await p.w.QcInspectionSheet.load();input().value='2026-11-06';input().dispatchEvent(new p.w.Event('input'));
  await new Promise(resolve=>setTimeout(resolve,720));
  const call=p.calls.find(c=>c.url==='api/inspection-sheet/entries/a/save');
  assert.deepEqual(call.body.inspectionExecution,{actualDate:'2026-11-06'});
  assert.equal(p.rows[0].inspectionExecution.reportNo,'KEEP');assert.equal(p.rows[0].dateFrom,'2026-10-29');
  await p.w.QcInspectionSheet.load();assert.equal(input().value,'2026-11-06');
  input().value='';input().dispatchEvent(new p.w.Event('change'));await p.w.QcInspectionSheet.flush();
  await p.w.QcInspectionSheet.load();assert.equal(input().value,'');assert.equal(p.rows[0].actualDate,'');
  assert.equal(p.rows[0].inspectionExecution.sampleQuantity,'0');
  p.w.__QC_NEXUS.workflow.edit=false;p.w.QcInspectionSheet.render();assert.equal(input(),null);
 }finally{p.dom.window.close();}
});

test('failed and conflicting date saves retain input, compare revisions and keep later edits in the queue',async()=>{
 const p=await page();try{
  const input=()=>p.d.querySelector('[data-entry="a"] [data-execution-field="actualDate"]');
  p.fail=true;input().value='2026-11-06';input().dispatchEvent(new p.w.Event('input'));await p.w.QcInspectionSheet.flush().catch(()=>{});
  assert.equal(input().value,'2026-11-06');assert.match(p.d.querySelector('[data-save-status="a"]').textContent,/保存失败/);
  await p.w.QcInspectionSheet.load();assert.equal(input().value,'2026-11-06');
  p.fail=false;const realFetch=p.w.fetch;let conflict=true;
  p.w.fetch=async(url,options)=>{if(conflict&&url.endsWith('/save')){conflict=false;p.rows[0].revision++;return {ok:false,status:409,json:async()=>({detail:'记录已更新'})};}return realFetch(url,options);};
  await p.w.QcInspectionSheet.retry('a');assert.equal(input().value,'2026-11-06');
  assert.equal(p.w.QcInspectionSheet.model.drafts.get('a').conflict,true);
  p.w.confirm=()=>false;await p.w.QcInspectionSheet.retry('a');assert.equal(p.rows[0].actualDate,undefined);
  p.w.confirm=()=>true;await p.w.QcInspectionSheet.retry('a');assert.equal(p.rows[0].actualDate,'2026-11-06');
  p.delay=40;input().value='2026-11-07';input().dispatchEvent(new p.w.Event('input'));input().dispatchEvent(new p.w.Event('blur'));
  await tick();input().value='2026-11-08';input().dispatchEvent(new p.w.Event('input'));await p.w.QcInspectionSheet.flush();
  assert.equal(p.rows[0].actualDate,'2026-11-08');assert.equal(p.maxActive,1);
 }finally{p.dom.window.close();}
});

test('immediate submit waits for the latest date and queued photo before sending its revision',async()=>{
 const p=await page();try{
  p.delay=40;p.w.QcInspectionSheet.edit('a','result','PASS',true);
  const input=p.d.querySelector('[data-entry="a"] [data-execution-field="actualDate"]');
  input.value='2026-11-09';input.dispatchEvent(new p.w.Event('input'));
  const row=p.d.querySelector('[data-entry="a"]');p.d.getElementById('page-records').classList.add('active');row.click();
  pasteEvent(p,row,[new p.w.File(['test'],'date-queue.png',{type:'image/png'})]);
  const original=p.w.fetch;let complete;
  const submittedRequest=new Promise(resolve=>complete=resolve);
  p.w.fetch=async(url,opts)=>{const response=await original(url,opts);if(url.endsWith('/submit'))complete();return response;};
  p.d.querySelector('[data-submit=a]').click();
  let timeout;try{await Promise.race([submittedRequest,new Promise((_,reject)=>timeout=setTimeout(()=>reject(new Error('Date/photo queue did not submit')),3000))]);}finally{clearTimeout(timeout);}
  await tick();assert.equal(p.d.querySelector('[data-entry="a"]'),null);
  const requests=p.calls.filter(c=>c.url?.includes('/entries/a/'));
  const submitted=requests.findIndex(c=>c.url.endsWith('/submit'));
  assert.ok(submitted>0);assert.ok(requests.findIndex(c=>c.url.endsWith('/photos'))<submitted);
  assert.equal(p.rows[0].actualDate,'2026-11-09');assert.equal(p.rows[0].photos.length,1);
  assert.equal(requests[submitted].body.revision,p.rows[0].revision-1);
 }finally{p.dom.window.close();}
});
