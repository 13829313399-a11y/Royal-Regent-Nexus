'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const project=process.env.QC_PROJECT_ROOT || path.resolve(__dirname,'../..');
const {JSDOM}=require(path.join(project,'node_modules/jsdom'));
const source=fs.readFileSync(path.join(__dirname,'qc-schedule.js'),'utf8');
const html=fs.readFileSync(path.join(project,'services/qc-department/index.html'),'utf8');
const sandbox={};vm.createContext(sandbox);vm.runInContext(source,sandbox);const api=sandbox.QcSchedule;
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/qc-schedule-example.json'),'utf8'));
const contract={factory_id:'huaxing',contract_version:'1',status:'mapping_required',items:[]};
const response=url=>({ok:true,json:async()=>JSON.parse(JSON.stringify({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:rows}))});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const base={from:'',to:'',customer:'',completion:'',query:''};
const rows=[
 {id:'1',dateFrom:'2026-10-27',dateTo:'2026-10-29',customer:'Dickie',poNo:'00123',productNo:'A',productName:'消防车',quantity:300,unitsPerCarton:6,cartonCount:50,completion:'已完成',remark:'箱唛待复核'},
 {id:'2',dateFrom:'2026-10-27',customer:'BUZZBEE',poNo:'00234',productNo:'B',productName:'水枪',quantity:7512,completion:'未验：待补件'},
 {id:'3',dateFrom:'2026-10-30',customer:'Dickie',poNo:'00345',productNo:'C',quantity:0,completion:'',remark:''},
 {id:'4',dateFrom:'',dateTo:'',customer:'Dickie',poNo:'00456',completion:'未填写',remark:'=HYPERLINK("https://example.invalid")'},
];
const ids=x=>Array.from(x,r=>r.id);
for(const [name,filters,want] of [
 ['all',{},['1','2','3','4']],['date only',{from:'2026-10-28',to:'2026-10-28'},['1']],
 ['customer only',{customer:'Dickie'},['1','3','4']],['completion only',{completion:'value:已完成'},['1']],
 ['date and customer',{from:'2026-10-27',to:'2026-10-27',customer:'BUZZBEE'},['2']],
 ['date and completion',{from:'2026-10-27',to:'2026-10-30',completion:'empty'},['3']],
 ['customer and completion',{customer:'Dickie',completion:'value:已完成'},['1']],
 ['three filters',{from:'2026-10-29',to:'2026-10-29',customer:'Dickie',completion:'value:已完成'},['1']],
 ['zero matches',{from:'2026-10-29',to:'2026-10-29',customer:'BUZZBEE',completion:'value:已完成'},[]],
 ['range left boundary',{from:'2026-10-26',to:'2026-10-27'},['1','2']],
 ['range right boundary',{from:'2026-10-29',to:'2026-10-30'},['1','3']],
 ['from only',{from:'2026-10-30'},['3']],['to only',{to:'2026-10-27'},['1','2']],
 ['search plus three filters',{from:'2026-10-29',to:'2026-10-29',customer:'Dickie',completion:'value:已完成',query:'消防'},['1']],
 ['literal unfilled is separate',{completion:'value:未填写'},['4']],
])test('independent/composed filtering: '+name,()=>{
 const before=JSON.stringify(rows);assert.deepEqual(ids(api.filterRows(rows,{...base,...filters})),want);assert.equal(JSON.stringify(rows),before);
});
test('invalid and reversed dates are rejected, unknown dates remain available without a date filter',()=>{
 for(const f of [{from:'2026-02-30'},{from:'2026-10-30',to:'2026-10-27'}])assert.throws(()=>api.filterRows(rows,{...base,...f}));
 assert.equal(api.dateRange({dateFrom:'2026-02-30'}),null);assert.equal(api.dateRange({dateFrom:'2026-10-29',dateTo:'2026-10-27'}),null);
});
test('free text completion values build distinct choices without a predefined status workflow',()=>{
 assert.deepEqual(new Set(api.choices(rows,'completion')),new Set(['已完成','未填写','未验：待补件']));
 assert.equal(api.filterRows(rows,{...base,completion:'empty'})[0].id,'3');
});
test('week selection uses complete Monday-to-Sunday interval including year boundaries',()=>{
 assert.deepEqual(JSON.parse(JSON.stringify(api.weekRange('2027-01-01',0))),{from:'2026-12-28',to:'2027-01-03'});
 assert.deepEqual(JSON.parse(JSON.stringify(api.weekRange('2026-10-26',1))),{from:'2026-11-02',to:'2026-11-08'});
});
test('cross-day records appear once and dates remain full-year values',()=>{
 const groups=api.groups(rows);assert.equal(groups.reduce((s,g)=>s+g.rows.length,0),4);
 assert.equal(groups[0].key,'2026-10-30');assert.equal(api.dateLabel(rows[0]),'2026-10-27 — 2026-10-29');
});
function xlsx(){const c={Uint8Array,ArrayBuffer};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(project,'services/qc-department/vendor/xlsx-js-style.min.js'),'utf8'),c);return c.XLSX;}
test('real XLSX round trip exports filtered rows, literal identifiers/notes, zero quantities and all 14 columns',()=>{
 const X=xlsx(),filtered=api.filterRows(rows,{...base,customer:'Dickie'}),wb=api.buildWorkbook(X,filtered,{...base,customer:'Dickie'},'华兴',false);
 const bytes=X.write(wb,{type:'array',bookType:'xlsx'}),saved=X.read(bytes,{type:'array'}),s=saved.Sheets['客排期'];
 assert.equal(s['!ref'],'A1:N7');assert.equal(s.C5.v,'00345');assert.equal(s.C5.t,'s');assert.equal(s.G5.v,0);assert.equal(s.G5.t,'n');
 assert.equal(s.N7.v,rows[3].remark);assert.equal(s.N7.t,'s');assert.equal(s.N7.f,undefined);
 assert.equal(s.M6.v,'已完成');assert.equal(s.N6.v,'箱唛待复核');assert.equal(s.N4.v,'备注');
 assert.equal(s['!autofilter'].ref,'A4:N7');
});
test('empty export has only template headers and never falls back to all source data',()=>{
 const X=xlsx(),f={...base,customer:'NO MATCH'},wb=api.buildWorkbook(X,api.filterRows(rows,f),f,'华兴',true),s=wb.Sheets['客排期'];
 assert.equal(s['!ref'],'A1:N4');assert.match(s.A1.v,/空模板，业务数据待接通/);assert.equal(s.A5,undefined);
});
async function page(exportAllowed=true,fetchImpl,optInExamples=true){
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/api/qc-department/huaxing/u-test/'});const w=dom.window;
 w.__QC_NEXUS={factory:'huaxing',exportAllowed};w.fetch=fetchImpl|| (async url=>response(url));w.showToast=()=>{};
 w.eval(source);await new Promise(resolve=>w.document.addEventListener('DOMContentLoaded',resolve,{once:true}));await w.renderSalesSchedule();
 return dom;
}
function captureExport(w){
 const result={}, originalFetch=w.fetch;w.XLSX=xlsx();const write=w.XLSX.write;
 w.XLSX.write=(wb,options)=>{result.wb=wb;return write(wb,options)};
 w.fetch=async(url,options)=>{
  if(!url.startsWith('api/schedule-export?'))return originalFetch(url,options);
  result.request={url,options};result.name=url.endsWith('example')?'QC客排期_示例数据.xlsx':'QC客排期_空模板.xlsx';
  return {ok:true,json:async()=>({url:'api/schedule-export/'+'a'.repeat(32)+'.1793000000.'+(url.endsWith('example')?'example':'template')+'.'+'b'.repeat(64),filename:result.name})};
 };
 w.document.addEventListener('click',e=>{if(e.target.tagName==='A'&&e.target.download){e.preventDefault();result.link=e.target.href;result.target=e.target.target}});
 return result;
}
test('date validation, clear and reset controls update independently',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
 d.getElementById('qsDateFrom').value='2026-10-30';d.getElementById('qsDateTo').value='2026-10-27';d.getElementById('qsDateTo').dispatchEvent(new w.Event('change'));
 assert.match(d.getElementById('qsFilterError').textContent,/开始日期/);assert.equal(d.getElementById('qsExport').disabled,true);
 d.getElementById('qsSearch').value='00123';d.getElementById('qsClearDates').click();assert.equal(d.getElementById('qsSearch').value,'00123');assert.equal(d.getElementById('qsFilterError').textContent,'');
 d.getElementById('qsReset').click();assert.equal(d.getElementById('qsSearch').value,'');
 d.getElementById('qsDateToggle').click();d.getElementById('qsThisWeek').click();d.getElementById('qsApplyDates').click();assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(d.getElementById('qsDateFrom').value));
 }finally{dom.window.close();}
});
test('compact date panel only applies on confirmation and preserves other filters',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.getElementById('qsDateLabel').textContent,'不限日期');
  d.getElementById('qsCustomer').value='Dickie';d.getElementById('qsCustomer').dispatchEvent(new w.Event('change'));
  const before=d.getElementById('qsRows').innerHTML;d.getElementById('qsDateToggle').click();
  assert.equal(d.getElementById('qsDateToggle').getAttribute('aria-expanded'),'true');assert.equal(d.activeElement.id,'qsDraftFrom');
  d.getElementById('qsDraftFrom').value='2026-10-28';d.getElementById('qsDraftTo').value='2026-10-28';
  d.getElementById('qsDraftTo').dispatchEvent(new w.Event('input'));assert.equal(d.getElementById('qsRows').innerHTML,before);assert.equal(d.getElementById('qsDateFrom').value,'');
  d.getElementById('qsApplyDates').click();assert.equal(d.getElementById('qsDateFrom').value,'2026-10-28');assert.equal(d.getElementById('qsDateLabel').textContent,'2026/10/28');
  assert.equal(d.getElementById('qsCustomer').value,'Dickie');assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.activeElement.id,'qsDateToggle');
  const shown=api.filterRows(rows,{...base,customer:'Dickie',from:'2026-10-28',to:'2026-10-28'});assert.equal(d.querySelectorAll('tr[data-qs-row]').length,shown.length);
 }finally{dom.window.close();}
});
test('date input losing focus to the page must not hide Confirm before its click is delivered',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  d.getElementById('qsDateToggle').click();d.getElementById('qsDraftFrom').value='2026-10-28';d.getElementById('qsDraftTo').value='2026-10-28';
  // Native date controls / non-focusable mouse targets may return focus to the document before click.
  d.getElementById('qsDraftFrom').dispatchEvent(new w.FocusEvent('focusout',{bubbles:true,relatedTarget:d.body}));
  assert.equal(d.getElementById('qsDatePanel').hidden,false,'Confirm must remain available until an explicit dismissal or confirmation');
  d.getElementById('qsApplyDates').click();
  assert.equal(d.getElementById('qsDateFrom').value,'2026-10-28');assert.equal(d.getElementById('qsDateLabel').textContent,'2026/10/28');
  // Fixture has 8 single-day rows plus 17 schedules spanning October 27-29.
  assert.equal(d.querySelectorAll('tr[data-qs-row]').length,1);assert.match(d.getElementById('qsCount').textContent,/1 \/ 4/);
  const exported=captureExport(w);d.getElementById('qsExport').click();await tick();
  assert.equal(exported.wb.Sheets['客排期']['!ref'],'A1:N5');
  d.getElementById('qsDateToggle').click();d.getElementById('qsDraftFrom').value='2030-01-01';d.getElementById('qsDraftTo').value='2030-01-02';d.getElementById('qsApplyDates').click();
  assert.equal(d.querySelectorAll('tr[data-qs-row]').length,0);assert.match(d.getElementById('qsCount').textContent,/0 \/ 4/);
 }finally{dom.window.close();}
});
test('outside click and Escape discard draft dates, while invalid ranges keep panel open',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  d.getElementById('qsDateToggle').click();d.getElementById('qsDraftFrom').value='2026-10-30';d.getElementById('qsDraftTo').value='2026-10-27';
  d.getElementById('qsApplyDates').click();assert.match(d.getElementById('qsDateError').textContent,/开始日期/);assert.equal(d.getElementById('qsDatePanel').hidden,false);
  assert.equal(d.getElementById('qsDateFrom').value,'');assert.equal(d.getElementById('qsExport').disabled,false);
  d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.activeElement.id,'qsDateToggle');
  d.getElementById('qsDateToggle').click();assert.equal(d.getElementById('qsDraftFrom').value,'');d.getElementById('qsDraftFrom').value='2026-10-28';d.getElementById('qsSearch').click();
  assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.getElementById('qsDateFrom').value,'');
 }finally{dom.window.close();}
});
test('date clear, one-sided range, Enter and full reset have distinct effects',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  d.getElementById('qsSearch').value='123';d.getElementById('qsDateToggle').click();d.getElementById('qsDraftFrom').value='2026-10-28';
  d.getElementById('qsDraftFrom').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));assert.equal(d.getElementById('qsDateLabel').textContent,'2026/10/28 起');
  d.getElementById('qsDateToggle').click();d.getElementById('qsClearDates').click();assert.equal(d.getElementById('qsSearch').value,'123');assert.equal(d.getElementById('qsDateLabel').textContent,'不限日期');
  d.getElementById('qsDateToggle').click();d.getElementById('qsNextWeek').click();assert.equal(d.getElementById('qsNextWeek').getAttribute('aria-pressed'),'true');assert.equal(d.getElementById('qsDateFrom').value,'');
  d.getElementById('qsReset').click();assert.equal(d.getElementById('qsSearch').value,'');assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.getElementById('qsDraftFrom').value,'');
 }finally{dom.window.close();}
});
test('export is denied without Nexus export permission',async()=>{
 const dom=await page(false);try{assert.equal(dom.window.document.getElementById('qsExport').disabled,true);}finally{dom.window.close();}
});
for(const payload of [{factory_id:'hy-other',contract_version:'1',status:'mapping_required',items:[]},{factory_id:'huaxing',contract_version:'1',status:'ready',items:rows}])test('unexpected data or wrong factory fails closed '+payload.status,async()=>{
 const dom=await page(true,async()=>({ok:true,json:async()=>payload}));try{const d=dom.window.document;assert.equal(d.getElementById('qsSourceStatus').textContent,'读取失败');assert.equal(d.getElementById('qsExport').disabled,true);assert.doesNotMatch(d.getElementById('qsRows').textContent,/消防车/);}finally{dom.window.close();}
});
test('network errors are visible and never presented as an empty connected schedule',async()=>{
 const dom=await page(true,async()=>{throw new Error('offline')});try{assert.match(dom.window.document.getElementById('qsNotice').textContent,/读取失败/);}finally{dom.window.close();}
});
test('customer whitespace is consistent between dynamic choices and filtering',()=>{
 const sample=[{...rows[0],customer:' Dickie '}];assert.equal(api.choices(sample,'customer')[0],'Dickie');assert.equal(api.filterRows(sample,{...base,customer:'Dickie'}).length,1);
});
test('untrusted objects cannot become workbook formulas or non-finite numeric values',()=>{
 const X=xlsx(),wb=api.buildWorkbook(X,[{...rows[0],remark:{t:'n',v:0,f:'1+2'},quantity:Infinity}],base,'华兴',false);
 const saved=X.read(X.write(wb,{type:'array',bookType:'xlsx'}),{type:'array'}).Sheets['客排期'];
 assert.equal(saved.N5.f,undefined);assert.equal(saved.N5.v,'');assert.equal(saved.G5.v,'');
});
test('export button creates only the labelled blank template in disconnected state',async()=>{
 const dom=await page(true,async()=>({ok:true,json:async()=>contract}));try{const call=captureExport(dom.window);dom.window.getCompanyName=()=> '华兴';dom.window.document.getElementById('qsExport').click();await tick();
 assert.equal(call.name,'QC客排期_空模板.xlsx');assert.match(call.wb.Sheets['客排期'].A1.v,/华兴.*空模板/);assert.equal(call.wb.Sheets['客排期']['!ref'],'A1:N4');
 }finally{dom.window.close();}
});

test('HTTP export sends the real workbook, uses an attachment URL and restores button after errors',async()=>{
 const dom=await page();try{const w=dom.window,d=w.document,captured=captureExport(w),messages=[];w.showToast=m=>messages.push(m);
 d.getElementById('qsExport').click();assert.equal(d.getElementById('qsExport').disabled,true);await tick();
 assert.equal(captured.request.options.method,'POST');assert.match(captured.request.options.headers['Content-Type'],/spreadsheetml/);
 const sheet=w.XLSX.read(captured.request.options.body,{type:'array'}).Sheets['客排期'];assert.equal(sheet['!ref'],'A1:N8');
 assert.match(captured.link,/http:\/\/localhost\/api\/qc-department\/huaxing\/u-test\/api\/schedule-export\//);assert.equal(captured.target,'_top');
 assert.equal(d.getElementById('qsExport').disabled,false);assert.match(messages.at(-1),/已发起/);
 captured.link=null;w.fetch=async()=>({ok:false,json:async()=>({detail:'下载服务暂不可用'})});
 d.getElementById('qsExport').click();await tick();assert.equal(captured.link,null);assert.equal(d.getElementById('qsExport').disabled,false);assert.equal(messages.at(-1),'下载服务暂不可用');
 }finally{dom.window.close()}
});
test('duplicate clicks prepare once and invalid download destinations are rejected',async()=>{
 const dom=await page();try{const w=dom.window,d=w.document,capture=captureExport(w),messages=[];let resolve,count=0;
 w.showToast=m=>messages.push(m);w.fetch=()=>{count++;return new Promise(r=>resolve=r)};
 d.getElementById('qsExport').click();d.getElementById('qsExport').click();assert.equal(count,1);
 resolve({ok:true,json:async()=>({url:'https://external.invalid/file.xlsx',filename:'file.xlsx'})});await tick();
 assert.equal(capture.link,undefined);assert.match(messages.at(-1),/下载地址无效/);assert.equal(d.getElementById('qsExport').disabled,false);
 }finally{dom.window.close()}
});

test('schedule feedback is read-only and each batch opens its own inspection, without selecting a push',async()=>{
 const formal={factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:[
  {id:'source-1',customer:'客户',productNo:'A',sourceStatus:'active',completion:'行验 首验：待审核',remark:'行验 首验：划痕 <script>bad()</script>',tasks:[
   {id:'task-1',method:'internal',batch:'首验',state:'pending',result:'PASS'},
   {id:'task-2',method:'external',batch:'复验',state:'returned',result:'REJ'}]},
  {id:'source-2',customer:'客户',productNo:'B',sourceStatus:'active',completion:'未推送',tasks:[]}]};
 const dom=await page(true,async()=>({ok:true,json:async()=>formal}));
 try {
  const w=dom.window,d=w.document,calls=[];w.QcWorkflow={openTask:(...args)=>calls.push(args)};
  const body=d.getElementById('qsRows');assert.equal(body.querySelector('.qs-cell-button'),null);assert.doesNotMatch(body.textContent,/✎|填写验货问题/);
  assert.match(body.textContent,/待审核/);assert.match(body.textContent,/已退回/);assert.match(body.textContent,/结果：PASS/);assert.match(body.textContent,/结果：REJECT/);
  assert.match(body.textContent,/未推送/);assert.equal(body.querySelector('script'),null);assert.match(body.textContent,/<script>/);
  const links=body.querySelectorAll('[data-qs-task]');assert.equal(links.length,2);links[0].click();links[1].click();
  assert.deepEqual(calls,[['task-1','records'],['task-2','records']]);assert.equal(body.querySelectorAll('[data-pick]:checked').length,0);
  assert.equal(body.querySelector('tr[data-qs-row="source-2"]').lastElementChild.textContent,'');
 }finally{dom.window.close();}
});

test('sample entry is absent and never fetched',async()=>{let urls=[];const dom=await page(true,async u=>{urls.push(u);return response(u)});try{assert.equal(dom.window.document.getElementById('qsExampleToggle'),null);assert.equal(urls.some(u=>u.includes('schedule-example')),false);}finally{dom.window.close()}});

test('partial push retains failed selection and filters; full success resets and sorts newest first',async()=>{
 const formal=rows.map(r=>({...r,sourceStatus:'active'}));const dom=await page(true,async()=>({ok:true,json:async()=>({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:formal})}));
 try{const w=dom.window,d=w.document;w.__QC_NEXUS.workflow={create:true};await w.renderSalesSchedule();
 d.getElementById('qsCustomer').value='Dickie';d.getElementById('qsCustomer').dispatchEvent(new w.Event('change'));
 d.querySelector('[data-pick="1"]').click();d.querySelector('[data-pick="3"]').click();
 await w.QcSchedule.afterPush(['1']);assert.equal(d.getElementById('qsCustomer').value,'Dickie');assert.deepEqual([...d.querySelectorAll('[data-pick]:checked')].map(e=>e.dataset.pick),['3']);
 await w.QcSchedule.afterPush(['3']);assert.equal(d.getElementById('qsCustomer').value,'');assert.equal(d.querySelectorAll('[data-pick]:checked').length,0);assert.equal(d.querySelector('tr[data-qs-row]').dataset.qsRow,'3');
 }finally{dom.window.close()}
});
