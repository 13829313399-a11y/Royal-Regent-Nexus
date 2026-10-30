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
  if(url.includes('/workbook/status'))return {ok:true,json:async()=>({version:bookVersion,undoAvailable:undo,count:rows.length,excluded:0,scope:{dateFrom:'2026-10-26',dateTo:'2026-11-01'}})};
  if(url.endsWith('/workbook/download'))return {ok:true,blob:async()=>new w.Blob(['saved-workbook'])};
  if(url.endsWith('/workbook/import')||url.endsWith('/workbook/undo')||url.endsWith('/workbook/replace')){assert.equal(body.expectedVersion,bookVersion);bookVersion++;undo=url.endsWith('/import');return {ok:true,json:async()=>({version:bookVersion,undoAvailable:undo,status:url.endsWith('/replace')?'replaced':undo?'imported':'undone',count:rows.length})};}
  if(url.endsWith('/photos')&&body.name==='corrupt.jpg')return {ok:false,status:422,json:async()=>({detail:'图片损坏或格式不支持'})};
  if(url.endsWith('/export'))return {ok:true,json:async()=>({url:'api/inspection-sheet/exports/'+'a'.repeat(32),filename:'test.xlsx'})};
  const id=url.split('/').at(-2),row=rows.find(r=>r.id===id);
  assert.ok(row,'stable entry identity');active++;maxActive=Math.max(maxActive,active);
  if(delay)await new Promise(resolve=>setTimeout(resolve,delay));
  const onlyInitialPhotos=url.includes('/workbook/entries/')&&body.revision+row.photos.length===row.revision&&row.result===''&&row.remark==='';
  if(!onlyInitialPhotos)assert.equal(body.revision,row.revision,'serialized requests use latest revision');
  if(url.endsWith('/save'))Object.assign(row,{result:body.result,remark:body.remark});
  if(url.endsWith('/photos'))row.photos.push({id:'photo-'+row.photos.length,name:body.name});
  if(url.endsWith('/remove-photo'))row.photos=row.photos.filter(p=>p.id!==body.photoId);
  row.revision++;active--;
  return {ok:true,json:async()=>copy(row)};
 };
 w.eval(script);await tick();if(!w.QcInspectionSheet.model.loaded)await w.QcInspectionSheet.load();
 return {dom,w,d:w.document,calls,get rows(){return rows;},set fail(value){fail=value;},set delay(value){delay=value;},get maxActive(){return maxActive;}};
}
test('16 template columns, inline three-result controls, reused remarks, real camera/file inputs and no drawer',async()=>{
 const p=await page();try{
  assert.equal(p.d.querySelectorAll('.qis-table thead th').length,16);
  assert.deepEqual([...p.d.querySelector('[data-result]').options].filter(x=>!x.disabled).map(x=>x.value),['PASS','FAIL','PENDING']);
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
  p.w.QcInspectionSheet.model.items[0].photoWarning='来源照片暂不可用；刷新重试';p.w.QcInspectionSheet.render();
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
