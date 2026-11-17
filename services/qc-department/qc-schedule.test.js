'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const project=process.env.QC_PROJECT_ROOT || path.resolve(__dirname,'../..');
const {JSDOM}=require(path.join(project,'node_modules/jsdom'));
const source=fs.readFileSync(path.join(__dirname,'qc-schedule.js'),'utf8');
const html=fs.readFileSync(path.join(project,'services/qc-department/index.html'),'utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const sandbox={};vm.createContext(sandbox);vm.runInContext(source,sandbox);const api=sandbox.QcSchedule;
const response=url=>({ok:true,json:async()=>JSON.parse(JSON.stringify({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:rows}))});
const base={from:'',to:'',customer:'',query:''};
const rows=[
 {id:'1',dateFrom:'2026-10-27',dateTo:'2026-10-29',customer:'Dickie',poNo:'00123',productNo:'A',productName:'消防车',quantity:300,unitsPerCarton:6,cartonCount:50,completion:'已完成',remark:'箱唛待复核'},
 {id:'2',dateFrom:'2026-10-27',customer:'BUZZBEE',poNo:'00234',productNo:'B',productName:'水枪',quantity:7512,completion:'未验：待补件'},
 {id:'3',dateFrom:'2026-10-30',customer:'Dickie',poNo:'00345',productNo:'C',quantity:0,completion:'',remark:''},
 {id:'4',dateFrom:'',dateTo:'',customer:'Dickie',poNo:'00456',completion:'未填写',remark:'=HYPERLINK("https://example.invalid")'},
];
const ids=x=>Array.from(x,r=>r.id);
for(const [name,filters,want] of [
 ['all',{},['1','2','3','4']],['date only',{from:'2026-10-28',to:'2026-10-28'},['1']],
 ['customer only',{customer:'Dickie'},['1','3','4']],
 ['date and customer',{from:'2026-10-27',to:'2026-10-27',customer:'BUZZBEE'},['2']],
 ['zero matches',{from:'2026-10-29',to:'2026-10-29',customer:'BUZZBEE'},[]],
 ['range left boundary',{from:'2026-10-26',to:'2026-10-27'},['1','2']],
 ['range right boundary',{from:'2026-10-29',to:'2026-10-30'},['1','3']],
 ['from only',{from:'2026-10-30'},['3']],['to only',{to:'2026-10-27'},['1','2']],
 ['search plus date and customer filters',{from:'2026-10-29',to:'2026-10-29',customer:'Dickie',query:'消防'},['1']],
])test('independent/composed filtering: '+name,()=>{
 const before=JSON.stringify(rows);assert.deepEqual(ids(api.filterRows(rows,{...base,...filters})),want);assert.equal(JSON.stringify(rows),before);
});
test('invalid and reversed dates are rejected, unknown dates remain available without a date filter',()=>{
 for(const f of [{from:'2026-02-30'},{from:'2026-10-30',to:'2026-10-27'}])assert.throws(()=>api.filterRows(rows,{...base,...f}));
 assert.equal(api.dateRange({dateFrom:'2026-02-30'}),null);assert.equal(api.dateRange({dateFrom:'2026-10-29',dateTo:'2026-10-27'}),null);
});
test('customer choices are distinct',()=>{
 assert.deepEqual(new Set(api.choices(rows,'customer')),new Set(['Dickie','BUZZBEE']));
});
test('week selection uses complete Monday-to-Sunday interval including year boundaries',()=>{
 assert.deepEqual(JSON.parse(JSON.stringify(api.weekRange('2027-01-01',0))),{from:'2026-12-28',to:'2027-01-03'});
 assert.deepEqual(JSON.parse(JSON.stringify(api.weekRange('2026-10-26',1))),{from:'2026-11-02',to:'2026-11-08'});
});
async function page(fetchImpl){
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/api/qc-department/huaxing/u-test/'});const w=dom.window;
 w.__QC_NEXUS={factory:'huaxing'};w.fetch=fetchImpl|| (async url=>response(url));w.showToast=()=>{};
 w.eval(source);await new Promise(resolve=>w.document.addEventListener('DOMContentLoaded',resolve,{once:true}));await w.renderSalesSchedule();
 return dom;
}
function showMonth(d,month) {
 if(d.getElementById('qsDatePanel').hidden)d.getElementById('qsDateToggle').click();
 const [year,number]=month.split('-').map(Number);
 for(let i=0;i<240;i++){
  const label=d.getElementById('qsCalendarMonth').getAttribute('aria-label').match(/(\d+)年(\d+)月/);
  const difference=(year-Number(label[1]))*12+number-Number(label[2]);
  if(!difference)return;
  d.getElementById(difference>0?'qsNextMonth':'qsPreviousMonth').click();
 }
 throw new Error('calendar month was unreachable');
}
function selectDate(d,value){showMonth(d,value.slice(0,7));d.querySelector('[data-qs-day="'+value+'"]').click();}
function selectRange(d,from,to=from){selectDate(d,from);selectDate(d,to);}
test('calendar starts unselected with a placeholder and only the Apply footer action',async()=>{
 const dom=await page();try{const d=dom.window.document;
  assert.equal(d.getElementById('qsDateLabel').textContent,'筛选日期');
  d.getElementById('qsDateToggle').click();
  assert.equal(d.getElementById('qsApplyDates').disabled,true);
  assert.equal(d.querySelectorAll('#qsCalendarDays [aria-selected="true"]').length,0);
  assert.equal(d.querySelectorAll('#qsCalendarDays button').length,42);
  assert.equal(d.querySelectorAll('#qsCalendarDays button[tabindex="0"]').length,1);
  assert.ok(d.activeElement.matches('[data-qs-day]'));
  assert.equal(d.querySelectorAll('.qs-date-footer button').length,1);
  assert.equal(d.querySelector('.qs-date-footer button').textContent,'应用');
  assert.doesNotMatch(d.getElementById('qsDatePanel').textContent,/今天及未来|上周|本周|下周|清除日期/);
 }finally{dom.window.close();}
});
test('calendar drafts do not fetch or change other filters; a same-day range applies on confirmation',async()=>{
 const calls=[],dom=await page(async url=>{calls.push(url);return response(url)});
 try{const d=dom.window.document,w=dom.window;
  d.getElementById('qsCustomer').value='Dickie';d.getElementById('qsCustomer').dispatchEvent(new w.Event('change'));
  const before=d.getElementById('qsRows').innerHTML,count=calls.length;
  selectDate(d,'2026-10-28');
  assert.equal(d.getElementById('qsApplyDates').disabled,true);
  assert.equal(d.getElementById('qsDatePanel').hidden,false,'redrawing clicked cells must not trigger outside dismissal');
  assert.equal(d.getElementById('qsDateFrom').value,'');
  selectDate(d,'2026-10-28');
  assert.equal(d.getElementById('qsRows').innerHTML,before);assert.equal(calls.length,count);
  assert.equal(d.getElementById('qsApplyDates').disabled,false);
  d.getElementById('qsApplyDates').click();await tick();
  assert.equal(calls.at(-1),'api/schedule-source?dateFrom=2026-10-28&dateTo=2026-10-28');
  assert.equal(d.getElementById('qsDateLabel').textContent,'10/28');
  assert.equal(d.getElementById('qsCustomer').value,'Dickie');
  assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.activeElement.id,'qsDateToggle');
  assert.equal(d.querySelectorAll('tr[data-qs-row]').length,1);
  d.getElementById('qsDateToggle').click();
  assert.equal(d.querySelectorAll('#qsCalendarDays [aria-selected="true"]').length,1);
 }finally{dom.window.close();}
});
test('reverse selection becomes an inclusive range across month/year boundaries',async()=>{
 const dom=await page();try{const d=dom.window.document;
  selectRange(d,'2027-01-02','2026-12-30');
  assert.equal(d.getElementById('qsDraftFrom').value,'2026-12-30');assert.equal(d.getElementById('qsDraftTo').value,'2027-01-02');
  assert.equal(d.querySelectorAll('#qsCalendarDays [aria-selected="true"]').length,4);
  d.getElementById('qsApplyDates').click();await tick();
  assert.equal(d.getElementById('qsDateLabel').textContent,'12/30 — 01/02');
  assert.equal(d.getElementById('qsDateToggle').title,'2026-12-30 至 2027-01-02');
  assert.equal(d.getElementById('qsCalendarMonth').textContent,'12月');
  assert.equal(d.getElementById('qsCalendarMonth').getAttribute('aria-label'),'2026年12月');
  selectDate(d,'2026-12-31');assert.equal(d.getElementById('qsDraftTo').value,'');
  assert.equal(d.getElementById('qsApplyDates').disabled,true,'a new first click starts a fresh range');
 }finally{dom.window.close();}
});
test('Escape and outside clicks discard drafts and focus movement does not hide Apply',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  selectRange(d,'2026-10-28');d.getElementById('qsApplyDates').click();await tick();
  selectRange(d,'2026-10-29','2026-10-30');
  d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.activeElement.id,'qsDateToggle');
  d.getElementById('qsDateToggle').click();assert.equal(d.getElementById('qsDraftFrom').value,'2026-10-28');
  selectDate(d,'2026-10-30');d.getElementById('qsSearch').click();
  assert.equal(d.getElementById('qsDatePanel').hidden,true);assert.equal(d.getElementById('qsDateFrom').value,'2026-10-28');
  selectRange(d,'2026-10-29');
  d.activeElement.dispatchEvent(new w.FocusEvent('focusout',{bubbles:true,relatedTarget:d.body}));
  assert.equal(d.getElementById('qsDatePanel').hidden,false);
  d.getElementById('qsApplyDates').click();await tick();assert.equal(d.getElementById('qsDateFrom').value,'2026-10-29');
 }finally{dom.window.close();}
});
test('calendar keyboard navigation handles leap days, weeks and month boundaries without applying',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  showMonth(d,'2028-02');assert.ok(d.querySelector('[data-qs-day="2028-02-29"]'));
  const day=d.querySelector('[data-qs-day="2028-02-29"]');day.focus();
  const key=k=>d.activeElement.dispatchEvent(new w.KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true}));
  key('ArrowRight');assert.equal(d.activeElement.dataset.qsDay,'2028-03-01');
  key('Home');assert.equal(d.activeElement.dataset.qsDay,'2028-02-28');
  key('End');assert.equal(d.activeElement.dataset.qsDay,'2028-03-05');
  key('ArrowDown');assert.equal(d.activeElement.dataset.qsDay,'2028-03-12');
  key('PageUp');assert.equal(d.activeElement.dataset.qsDay,'2028-02-12');
  key('PageDown');assert.equal(d.activeElement.dataset.qsDay,'2028-03-12');
  assert.equal(d.getElementById('qsDraftFrom').value,'');assert.equal(d.getElementById('qsDateFrom').value,'');
 }finally{dom.window.close();}
});
test('reset clears both calendar selection and all filters; invalid external ranges remain rejected',async()=>{
 const dom=await page();try{const d=dom.window.document,w=dom.window;
  d.getElementById('qsDateFrom').value='2026-10-30';d.getElementById('qsDateTo').value='2026-10-27';d.getElementById('qsDateTo').dispatchEvent(new w.Event('change'));
  assert.match(d.getElementById('qsFilterError').textContent,/开始日期/);
  d.getElementById('qsSearch').value='00123';d.getElementById('qsReset').click();await tick();
  assert.equal(d.getElementById('qsSearch').value,'');assert.equal(d.getElementById('qsFilterError').textContent,'');
  selectRange(d,'2026-10-27','2026-10-29');d.getElementById('qsApplyDates').click();await tick();
  d.getElementById('qsReset').click();await tick();assert.equal(d.getElementById('qsDateLabel').textContent,'筛选日期');
  assert.equal(d.getElementById('qsDatePanel').hidden,true);d.getElementById('qsDateToggle').click();
  assert.equal(d.getElementById('qsDraftFrom').value,'');assert.equal(d.getElementById('qsApplyDates').disabled,true);
 }finally{dom.window.close();}
});
for(const payload of [{factory_id:'hy-other',contract_version:'1',status:'mapping_required',items:[]},{factory_id:'huaxing',contract_version:'1',status:'ready',items:rows}])test('unexpected data or wrong factory fails closed '+payload.status,async()=>{
 const dom=await page(async()=>({ok:true,json:async()=>payload}));try{const d=dom.window.document;assert.match(d.getElementById('qsRows').textContent,/读取失败/);assert.doesNotMatch(d.getElementById('qsRows').textContent,/消防车/);}finally{dom.window.close();}
});
test('network errors are visible and never presented as an empty connected schedule',async()=>{
 const dom=await page(async()=>{throw new Error('offline')});try{assert.match(dom.window.document.getElementById('qsRows').textContent,/读取失败/);}finally{dom.window.close();}
});
test('customer whitespace is consistent between dynamic choices and filtering',()=>{
 const sample=[{...rows[0],customer:' Dickie '}];assert.equal(api.choices(sample,'customer')[0],'Dickie');assert.equal(api.filterRows(sample,{...base,customer:'Dickie'}).length,1);
});
test('schedule feedback is read-only and each batch opens its own inspection, without selecting a push',async()=>{
 const formal={factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:[
  {id:'source-1',customer:'客户',productNo:'A',sourceStatus:'active',completion:'行验 首验：待审核',remark:'行验 首验：划痕 <script>bad()</script>',tasks:[
   {id:'task-1',method:'internal',batch:'首验',state:'pending',result:'PASS'},
   {id:'task-2',method:'external',batch:'复验',state:'returned',result:'REJ'}]},
  {id:'source-2',customer:'客户',productNo:'B',sourceStatus:'active',completion:'未推送',tasks:[]}]};
 const dom=await page(async()=>({ok:true,json:async()=>formal}));
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

test('sample entry is absent and never fetched',async()=>{let urls=[];const dom=await page(async u=>{urls.push(u);return response(u)});try{assert.equal(dom.window.document.getElementById('qsExampleToggle'),null);assert.equal(urls.some(u=>u.includes('schedule-example')),false);}finally{dom.window.close()}});

test('date confirmation fetches historical business rows and reset fetches the default scope again',async()=>{
 const calls=[],future={...rows[2],customer:'Future customer'},past={...rows[0],customer:'Past customer'};
 const payload=items=>({ok:true,json:async()=>({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items})});
 const dom=await page(async url=>{calls.push(url);return payload(url.includes('?')?[past]:[future]);});
 try{const w=dom.window,d=w.document;
  assert.deepEqual([...d.querySelectorAll('[data-qs-row]')].map(r=>r.dataset.qsRow),['3']);
  d.getElementById('qsCustomer').value='Future customer';d.getElementById('qsCustomer').dispatchEvent(new w.Event('change'));
  const before=calls.length;
  selectRange(d,'2026-10-28');
  assert.equal(calls.length,before,'draft dates do not fetch until confirmed');
  d.getElementById('qsApplyDates').click();await tick();
  assert.equal(calls.at(-1),'api/schedule-source?dateFrom=2026-10-28&dateTo=2026-10-28');
  assert.equal(d.getElementById('qsCustomer').value,'Future customer');
  assert.equal(d.querySelectorAll('[data-qs-row]').length,0,'date changes must not silently broaden the customer filter');
  d.getElementById('qsCustomer').value='';d.getElementById('qsCustomer').dispatchEvent(new w.Event('change'));
  assert.equal(d.querySelector('[data-qs-row]').dataset.qsRow,'1');
  assert.equal(calls.length,before+1,'customer filtering stays within the fetched date scope');
  d.getElementById('qsRefresh').click();await tick();assert.match(calls.at(-1),/dateFrom=2026-10-28/);
  await w.QcSchedule.resetFilters();assert.equal(calls.at(-1),'api/schedule-source');
  assert.equal(d.getElementById('qsDateLabel').textContent,'筛选日期');assert.equal(d.querySelector('[data-qs-row]').dataset.qsRow,'3');
 }finally{dom.window.close();}
});

test('late history response cannot replace a newer default-scope response',async()=>{
 let release;
 const payload=items=>({ok:true,json:async()=>({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items})});
 const dom=await page(url=>url.includes('?')?new Promise(resolve=>{release=()=>resolve(payload([rows[0]]));}):Promise.resolve(payload([rows[2]])));
 try{const w=dom.window,d=w.document;
  selectRange(d,'2026-10-28');d.getElementById('qsApplyDates').click();
  await w.QcSchedule.resetFilters();release();await tick();
  assert.equal(d.querySelector('[data-qs-row]').dataset.qsRow,'3');assert.equal(d.getElementById('qsDateLabel').textContent,'筛选日期');
 }finally{dom.window.close();}
});

test('partial push retains failed selection and filters; full success resets and sorts earliest first',async()=>{
 const formal=rows.map(r=>({...r,sourceStatus:'active'}));const dom=await page(async()=>({ok:true,json:async()=>({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items:formal})}));
 try{const w=dom.window,d=w.document;w.__QC_NEXUS.workflow={create:true};await w.renderSalesSchedule();
 d.getElementById('qsCustomer').value='Dickie';d.getElementById('qsCustomer').dispatchEvent(new w.Event('change'));
 d.querySelector('[data-pick="1"]').click();d.querySelector('[data-pick="3"]').click();
 await w.QcSchedule.afterPush(['1']);assert.equal(d.getElementById('qsCustomer').value,'Dickie');assert.deepEqual([...d.querySelectorAll('[data-pick]:checked')].map(e=>e.dataset.pick),['3']);
 await w.QcSchedule.afterPush(['3']);assert.equal(d.getElementById('qsCustomer').value,'');assert.equal(d.querySelectorAll('[data-pick]:checked').length,0);assert.equal(d.querySelector('tr[data-qs-row]').dataset.qsRow,'2');
 }finally{dom.window.close()}
});

test('every schedule row shows its date, including repeated dates and ranges', async () => {
 const items = [
  {id:'a',dateFrom:'2026-12-22',customer:'A',productNo:'A',sourceStatus:'active'},
  {id:'b',dateFrom:'2026-12-22',customer:'B',productNo:'B',sourceStatus:'active'},
  {id:'week',dateFrom:'2026-11-16',dateTo:'2026-11-19',productNo:'W',sourceStatus:'active'},
  {id:'range',dateFrom:'2025-12-31',dateTo:'2026-01-02',productNo:'R',sourceStatus:'active'},
  {id:'missing',dateFrom:'',productNo:'M',sourceStatus:'cancelled'},
 ];
 const dom = await page(async () => ({ok:true,json:async()=>({factory_id:'huaxing',contract_version:'2',status:'ready',mapping_version:'qc-task-v1',source_available:true,items})}));
 try {
  const w=dom.window,d=w.document;
  w.__QC_NEXUS.workflow={create:true};await w.renderSalesSchedule();
  assert.equal(d.querySelectorAll('#qsRows .qs-group').length,0);
  assert.equal(d.querySelectorAll('#qsRows tr').length,5);
  const dates=d.querySelectorAll('#qsRows .qs-date-cell');
  assert.equal(dates.length,5);
  assert.ok([...dates].every(cell=>cell.rowSpan===1));
  assert.match(dates[0].textContent,/12月31日2025 · 周三至01月02日2026 · 周五/);
  assert.match(dates[1].textContent,/11月16–19日2026 · 周一至周四/);
  assert.match(dates[2].textContent,/12月22日2026 · 周二/);
  assert.equal(dates[3].textContent,dates[2].textContent);
  assert.equal(dates[4].textContent,'待确认');
  d.querySelector('[data-pick="b"]').click();
  assert.equal(d.querySelector('[data-pick="b"]').checked,true);
  assert.equal(d.querySelector('[data-pick="a"]').checked,false);
  assert.equal(d.querySelector('[data-pick="missing"]').disabled,true);
  const customer=d.getElementById('qsCustomer');customer.value='B';customer.dispatchEvent(new w.Event('change'));
  assert.equal(d.querySelector('.qs-date-cell').rowSpan,1);
  assert.equal(d.querySelector('[data-pick="b"]').checked,false);
 } finally { dom.window.close(); }
});
