const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const key='a'.repeat(64),entry='c'.repeat(32),field='detail:'+entry+':contractNo';
const titles={caixing:'彩星月度验货明细及汇总表',all:'月度验货明细表（全客户）',issues:'月度验货问题图文记录表',customers:'月度验货明细表（按客户）'};
const fixture=()=>{
 const row={id:entry,customerKey:key,photos:[{id:'photo1',name:'合成照片'}],poNo:'TEST',values:[1,'2026-11-05','彩星','','UK','SKU','产品',100,'10','10','PASS','有','生产','机构','问题','甲','乙','备注'],editableFields:{3:field}};
 const project=(idx)=>({...row,values:idx.map(i=>row.values[i]),editableFields:{[idx.indexOf(3)]:field}});
 return {date:'2026-11-01',dateFrom:'2026-11-01',dateTo:'2026-11-30',sourceRevision:'b'.repeat(64),canEdit:true,canExport:true,total:1,scheduleCount:0,
 templates:Object.entries(titles).map(([id,title])=>({id,title,headers:Array(id==='caixing'?13:id==='issues'?12:18).fill('字段'),sourceFile:'原始模板'})),summaryHeaders:['月份','验货总单数','合格单数','实际退货次数','不良率'],customers:[{key,name:'彩星',label:'彩星 · A'}],
 fields:{[key]:{[field]:{value:'',version:0},returns:{value:'',version:0}}},tables:{all:[row],customers:[row],caixing:[project([1,2,3,4,5,6,7,8,9,10,14,17,17])],issues:[project([1,2,3,5,6,7,8,9,10,14,12,17])],summary:[{id:key,customerKey:key,values:['2026-11',1,1,'',''],editableFields:{3:'returns'}}]}};
};
function page(storage){
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),{url:'http://localhost/api/qc-department/huaxing/u-test/',runScripts:'outside-only'}),w=dom.window,d=w.document,data=fixture(),calls=[];
 w.__QC_NEXUS={factory:'huaxing'};d.getElementById('monthlyMonth').value='2026-11';w.showToast=()=>{};
 const response=(v,status=200)=>({ok:status===200,status,json:async()=>JSON.parse(JSON.stringify(v))});
 w.fetch=async(url,init)=>{calls.push({url,init});if(!init.body)return response(data);const b=JSON.parse(init.body);data.fields[b.customerKey][b.field]={value:b.value,version:b.baseVersion+1};return response({...b,version:b.baseVersion+1});};
 if(storage)for(const [k,v]of Object.entries(storage))w.localStorage.setItem(k,v);
 w.eval(fs.readFileSync(path.join(__dirname,'qc-monthly-templates.js'),'utf8'));d.dispatchEvent(new w.Event('DOMContentLoaded'));
 const edit=(f,v)=>{d.querySelector('[data-field="'+f+'"]').click();const e=d.querySelector('.qmt-editor');e.value=v;e.dispatchEvent(new w.Event('input',{bubbles:true}));return e;};
 return {dom,w,d,data,calls,response,edit};
}
test('four independent layouts, month query, photos and return through 月',async()=>{
 const p=page();try{
 assert.equal(p.d.querySelectorAll('#qmtEntries button').length,4);
 for(const k of Object.keys(titles)){await p.w.QcMonthlyTemplates.open(k);assert.match(p.calls.at(-1).url,/date=2026-11-01/);assert.equal(p.d.querySelectorAll('#qmtTables table')[0].querySelectorAll('thead tr:last-child th').length,k==='caixing'?13:k==='issues'?12:18);assert.equal(p.d.querySelectorAll('#qmtTables [colspan],#qmtTables [rowspan]').length,0);}
 await p.w.QcMonthlyTemplates.open('issues');assert.equal(p.d.querySelectorAll('.qmt-photo img').length,1);
 assert.ok(p.w.QcMonthlyTemplates.returnToReport());assert.equal(p.d.getElementById('monthlyReportBody').hidden,false);
 }finally{p.dom.window.close();}
});
test('blank editing, autosave, switching and saved values on reload',async()=>{
 const p=page();try{await p.w.QcMonthlyTemplates.open('all');p.edit(field,'00123').dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await p.w.QcMonthlyTemplates.flush();assert.equal(p.w.QcMonthlyTemplates.navigationState().dirty,false);
 for(const k of ['caixing','issues','customers']){await p.w.QcMonthlyTemplates.open(k);assert.equal(p.d.querySelector('[data-field="'+field+'"]').textContent,'00123');}
 await p.w.QcMonthlyTemplates.open('caixing');p.edit('returns','2');await p.w.QcMonthlyTemplates.flush();p.d.querySelector('.qmt-editor').blur();assert.equal(p.d.querySelectorAll('#qmtTables table')[1].querySelector('tbody tr td:last-child').textContent,'');
 }finally{p.dom.window.close();}
});
test('failed save preserves exact request and blocks month/page changes',async()=>{
 const p=page();let saved,req;try{await p.w.QcMonthlyTemplates.open('caixing');p.edit('returns','3').blur();p.w.fetch=async(_,init)=>{req=JSON.parse(init.body);throw Error('断网');};await p.w.QcMonthlyTemplates.flush();assert.match(p.d.getElementById('qmtStatus').textContent,/断网/);assert.equal(p.w.QcMonthlyTemplates.returnToReport(),false);
 const date=p.d.getElementById('monthlyMonth');date.value='2026-12';date.dispatchEvent(new p.w.Event('change'));assert.equal(date.value,'2026-11');saved=Object.fromEntries(Object.keys(p.w.localStorage).map(k=>[k,p.w.localStorage.getItem(k)]));
 }finally{p.dom.window.close();}
 const q=page(saved);try{await q.w.QcMonthlyTemplates.open('caixing');assert.equal(q.d.querySelector('[data-field="returns"]').textContent,'3');let retry;q.w.fetch=async(_,init)=>{retry=JSON.parse(init.body);return q.response({...retry,version:1});};q.d.getElementById('qmtRetry').click();await new Promise(r=>setTimeout(r,20));assert.deepEqual(retry,req);assert.equal(q.w.QcMonthlyTemplates.navigationState().dirty,false);}finally{q.dom.window.close();}
});
test('export current template, no writes before export, empty state disables download',async()=>{
 const p=page();try{p.w.HTMLAnchorElement.prototype.click=function(){};await p.w.QcMonthlyTemplates.open('issues');let request;p.w.fetch=async(_,init)=>{request=JSON.parse(init.body);return p.response({url:'api/monthly-templates/excel/abc',filename:'问题表.xlsx'});};p.d.getElementById('qmtExcel').click();await new Promise(r=>setTimeout(r,20));assert.equal(request.template,'issues');assert.equal(request.date,'2026-11-01');assert.match(p.d.getElementById('qmtExcelStatus').textContent,/已生成/);
 p.data.tables.caixing=[];p.data.tables.summary=[];p.w.fetch=async()=>p.response(p.data);await p.w.QcMonthlyTemplates.open('caixing');assert.equal(p.d.getElementById('qmtExcel').disabled,true);assert.match(p.d.getElementById('qmtTables').textContent,/没有符合/);
 }finally{p.dom.window.close();}
});

test('photo quality chooser defaults to preview, blocks missing originals without consent and cancels without export',async()=>{
 const p=page();try{
  p.w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};p.w.HTMLDialogElement.prototype.close=function(){this.open=false;};p.w.HTMLAnchorElement.prototype.click=function(){};
  await p.w.QcMonthlyTemplates.open('issues');const exports=[];
  p.w.fetch=async(url,init)=>{if(url.endsWith('/options'))return p.response({count:2,missingOriginals:1,displayConversions:0});exports.push(JSON.parse(init.body));return p.response({url:'api/monthly-templates/excel/abc',filename:'测试.xlsx'});};
  const wait=()=>new Promise(r=>setTimeout(r,20));
  p.d.getElementById('qmtExcel').click();await wait();let dlg=p.d.querySelector('dialog');assert.equal(dlg.querySelector('[value=preview]').checked,true);
  dlg.querySelector('[data-cancel]').click();await wait();assert.equal(exports.length,0);assert.equal(p.d.querySelector('dialog'),null);
  p.d.getElementById('qmtExcel').click();await wait();dlg=p.d.querySelector('dialog');dlg.querySelector('[value=original]').click();assert.equal(dlg.querySelector('[data-confirm]').disabled,true);
  dlg.querySelector('[data-fallback] input').click();dlg.querySelector('[data-confirm]').click();await wait();assert.equal(exports[0].photoQuality,'original');assert.equal(exports[0].allowPreviewFallback,true);
  p.data.tables.issues[0].photos=[];p.w.fetch=async(url,init)=>{if(!init?.body)return p.response(p.data);assert.ok(!url.endsWith('/options'));exports.push(JSON.parse(init.body));return p.response({url:'api/monthly-templates/excel/abc',filename:'测试.xlsx'});};
  await p.w.QcMonthlyTemplates.open('issues');p.d.getElementById('qmtExcel').click();await wait();assert.equal(p.d.querySelector('dialog'),null);assert.equal(exports.length,2);assert.equal(exports[1].photoQuality,undefined);
 }finally{p.dom.window.close();}
});
