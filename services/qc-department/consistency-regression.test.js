'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const app = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
const report = fs.readFileSync(path.join(__dirname, 'report_export.js'), 'utf8');
function functionSource(source, name) {
  const start = source.search(new RegExp('(?:async )?function ' + name + '\\('));
  assert.ok(start >= 0, name);
  return source.slice(start, source.indexOf('\n}', start) + 2);
}
function browser(appSource = app, reportSource = report) {
  const elements = new Map(), store = new Map();
  const element = () => ({ value: '', innerHTML: '', textContent: '', style: {}, dataset: {},
    classList: {add(){},remove(){},toggle(){}}, appendChild(){}, setAttribute(){}, addEventListener(){} });
  const get = id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
  const ctx = {console, setInterval(){}, setTimeout(){}, clearTimeout(){}, addEventListener(){}, navigator:{},
    document:{getElementById:get,querySelectorAll:()=>[],querySelector:()=>null,createElement:element,addEventListener(){}},
    sessionStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
    localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
    location:{pathname:'/api/qc-department/huaxing/u-audit/'},
    fetch(){throw Error('Unexpected network request')},
    confirm(){throw Error('Unexpected confirmation')}
  };
  ctx.window=ctx;ctx.__QC_NEXUS={};vm.createContext(ctx);
  vm.runInContext(appSource,ctx);vm.runInContext(reportSource,ctx);
  return {ctx,get,store,run:s=>vm.runInContext(s,ctx)};
}
for (const type of ['Daily','Weekly']) test(type+' PDF content retains dynamic company/reference header without legacy company subtitle',()=>{
  const b=browser();b.get('dailyDate').value='2026-10-19';b.get('weeklyDate').value='2026-10-19';
  b.run(`state={records:[],nextId:31};getCompanyName=()=> 'Huaxing <Factory>';window.__QC_REFERENCE_DATA={count:30};`);
  const html=b.ctx['_build'+type+'Canvas'](false).innerHTML;
  assert.match(html,/Huaxing &lt;Factory&gt;/);
  assert.match(html,/模板参考（非本厂实绩）/);
  assert.doesNotMatch(html,/东\s*莞\s*兴\s*信/);
});
test('explicit record refresh replaces loaded partner cache and candidates without any business POST',async()=>{
  const b=browser(),records=[{id:1,date:'2026-10-19',result:'PASS',supplier:'Original'}];
  b.ctx.records=records;
  b.run(`state={records, nextId:31};_partners=[{type:'supplier',name:'Stale'}];getCompany=()=> 'hy-huaxing';filterRecords=()=>{};updateTopKpis=()=>{};showToast=()=>{};`);
  let requests=0;
  b.ctx.fetch=async(url,options)=>{
    requests++;assert.equal(options.method,undefined);assert.match(url,/api\/bootstrap\?company=hy-huaxing$/);
    return {ok:true,json:async()=>({records,nextId:31,partners:[{type:'supplier',name:'New supplier'},{type:'customer',name:'New customer'},{type:'processType',name:'New process'}]})};
  };
  await b.ctx.refreshRecordsPage();
  assert.equal(requests,1);
  assert.deepEqual(JSON.parse(b.run('JSON.stringify(managedNames("supplier"))')),['New supplier']);
  assert.match(b.get('supplierList').innerHTML,/New supplier/);
  assert.match(b.get('customerList').innerHTML,/New customer/);
  assert.match(b.get('processTypeList').innerHTML,/New process/);
  assert.deepEqual(JSON.parse(b.run('JSON.stringify(state.records)')),records);
});
test('cancelled record refresh preserves existing partner cache',async()=>{
  const b=browser();b.run(`state={records:[],nextId:31};_partners=[{type:'supplier',name:'Keep'}];getCompany=()=> 'hy-huaxing';showToast=()=>{};`);
  b.ctx.confirm=()=>false;b.ctx.fetch=async()=>({ok:true,json:async()=>({records:[{id:1}],partners:[{type:'supplier',name:'Discard'}]})});
  await b.ctx.refreshRecordsPage();
  assert.equal(b.run('managedNames("supplier")[0]'),'Keep');
});

test('daily and weekly pages and PDF contents include the same recorded problem notes without interpreting markup',()=>{
  const b=browser();b.get('dailyDate').value='2026-10-19';b.get('weeklyDate').value='2026-10-19';
  b.run(`state={records:[{id:42,date:'2026-10-19',inspDate:'2026-10-19',supplier:'S',productNo:'P',type:'成品',qty:100,sampleQty:10,result:'PASS',status:'approved',remark:'Check <tag> & label',defects:[{desc:'Surface',qty:1,remark:'Verify seam'}]}],nextId:43};getCompanyName=()=> 'Huaxing';`);
  const before=b.run('JSON.stringify(state.records)');
  b.ctx.renderDailyReport();b.ctx.renderWeeklyReport();
  const html=[b.get('dailyReportBody').innerHTML,b.get('weeklyReportBody').innerHTML,
    b.ctx._buildDailyCanvas().innerHTML,b.ctx._buildWeeklyCanvas(false).innerHTML];
  for(const text of html){
    assert.match(text,/验货问题备注（原文）/);assert.match(text,/Check &lt;tag&gt; &amp; label/);
    assert.match(text,/Surface：Verify seam/);assert.doesNotMatch(text,/<tag>/);
  }
  assert.equal(b.run('JSON.stringify(state.records)'),before);
});

test('empty notes add no report section',()=>{
  const b=browser();assert.equal(b.ctx.buildQcProblemNotes([{id:1,remark:' ',defects:[]}]),'');
});

for (const type of ['Daily','Weekly']) test(type+' PDF quantity totals are numeric without changing source records',()=>{
  const b=browser();b.get('dailyDate').value='2026-10-19';b.get('weeklyDate').value='2026-10-19';
  b.run(`state={records:[{id:1,date:'2026-10-19',qty:'100',result:'PASS',status:'approved'}, {id:2,date:'2026-10-19',qty:'200',result:'PASS',status:'approved'}],nextId:3};getCompanyName=()=> 'Huaxing';`);
  const before=b.run('JSON.stringify(state.records)');
  const html=b.ctx['_build'+type+'Canvas'](false).innerHTML;
  assert.match(html,/300/);assert.doesNotMatch(html,/0100200/);
  assert.equal(b.run('JSON.stringify(state.records)'),before);
});

for (const page of ['records','dashboard']) test('local CSV keeps a zero-match filter empty on '+page,()=>{
  const b=browser();b.get('searchInput').value='does-not-exist';let csv='';
  b.ctx.Blob=class { constructor(parts){csv=parts.join('')} };
  b.ctx.URL={createObjectURL:()=> 'blob:audit',revokeObjectURL(){}};
  b.ctx.document.body={appendChild(){},removeChild(){}};
  b.ctx.document.createElement=()=>({click(){}});
  b.run(`currentPage=${JSON.stringify(page)};state={records:[{id:1,date:'2026-10-19',supplier:'Must not export',result:'PASS'}],nextId:2};can=()=>true;filterRecords=()=>{filteredRecs=[]};_downloadServerExport=()=>false;showToast=()=>{};getCompanyName=()=> 'Huaxing';`);
  b.ctx.exportCSV();assert.ok(csv.length>0);assert.equal(csv.split('\n').length,1);assert.doesNotMatch(csv,/Must not export/);
});

test('deferred date, PASS and average/risk semantics remain unchanged',()=>{
  const b=browser();
  b.get('dailyDate').value='2026-10-20';b.get('weeklyDate').value='2026-10-19';
  b.run(`state={records:[{id:1,date:'2026-10-19',inspDate:'2026-10-20',result:'PASS',status:'approved',qty:1},{id:2,date:'2026-10-19',result:'COND',status:'approved',qty:1},{id:3,date:'2026-10-19',result:'HOLD',status:'approved',qty:1},{id:4,date:'2026-10-19',result:'REJ',status:'approved',qty:1}],nextId:5};getCompanyName=()=> 'Huaxing';`);
  b.ctx.renderDailyReport();b.ctx.renderWeeklyReport();
  assert.match(b.get('dailyReportBody').innerHTML,/验货批次<\/div><div class="meta-value">1 批/);
  assert.match(b.get('weeklyReportBody').innerHTML,/PASS 批次<\/div><div class="meta-value text-green">3 批/);
  assert.match(b.ctx._buildWeeklyCanvas(false).innerHTML,/1 \/ 4 批次通过/);
  assert.equal(b.ctx._defectRateAvg([{sampleQty:0,defectRate:'0%'},{sampleQty:100,defectRate:'10%'}]).avg,5);
  assert.equal(b.ctx.getRisk(.15),'high');assert.equal(b.ctx.getRisk(.05),'mid');
});

for(const result of ['PASS','REJ','FAIL','COND','HOLD']) for(const withAppendix of [false,true]) {
  test('weekly PDF keeps notes exactly once for '+result+' withAppendix='+withAppendix,()=>{
    const b=browser();b.get('weeklyDate').value='2026-10-19';
    b.ctx.fixture={id:1,date:'2026-10-19',supplier:'S',productNo:'P',qty:100,sampleQty:10,fail:2,defectRate:'20%',result,status:'approved',remark:'Keep this problem note',defects:[{desc:'Surface',qty:2,remark:'Keep this defect note'}]};
    b.run(`state={records:[fixture,{...fixture,id:2,status:'pending',remark:'UNAPPROVED note',defects:[]}],nextId:3};getCompanyName=()=> 'Huaxing';`);
    const html=b.ctx._buildWeeklyCanvas(withAppendix).innerHTML;
    assert.equal(html.split('Keep this problem note').length-1,1);
    assert.equal(html.split('Keep this defect note').length-1,1);
    assert.doesNotMatch(html,/UNAPPROVED note/);
  });
}

for(const raw of ['',null,'unknown','2026-02-30','2025/02/29','2026年13月1日','5月4日','04/05/2026','45000junk','2026-02-30T10:00:00Z']) test('unrecognized date stays blank: '+raw,()=>{
  const b=browser();assert.equal(b.ctx._dateDisplay(raw),'');
});
for(const [raw,want] of [['2024-02-29','2024-02-29'],['2026/4/9','2026-04-09'],['2026年 4 月 9 日','2026-04-09'],['2026.10.19','2026-10-19'],['19/10/2026','2026-10-19'],['10/19/2026','2026-10-19'],['11/11/2026','2026-11-11'],[45000.75,'2023-03-15']]) test('recognized date: '+raw,()=>{
  const b=browser();assert.equal(b.ctx._dateDisplay(raw),want);
});
test('editing unrelated fields preserves raw historical invalid date; explicit date edits replace it',()=>{
  const b=browser();b.ctx._setRecordDateInput('f_date','2026-02-30',true);
  assert.equal(b.get('f_date').value,'');assert.equal(b.ctx._recordDateValue('f_date'),'2026-02-30');
  b.get('f_date').value='2026-02-28';b.get('f_date').oninput();assert.equal(b.ctx._recordDateValue('f_date'),'2026-02-28');
  b.ctx._setRecordDateInput('f_date','',false);assert.equal(b.ctx._recordDateValue('f_date'),'');
});
test('Excel import independently keeps unknown arrival/inspection dates blank without changing current records',()=>{
  const b=browser();b.run(`state={records:[{id:9,date:'2026-01-01'}],nextId:10};_importMappedFields={A:'date',B:'inspDate',C:'supplier'};_importWarnings=[];
    _importParsedRows=[{A:'2026-02-30',B:'2026-03-01',C:'S'},{A:'2026-04-01',B:'',C:'S'},{A:'',B:'',C:'S'}];`);
  const before=b.run('JSON.stringify(state)');const plan=b.ctx._buildImportPlan('append');
  assert.equal(plan.records.length,3);assert.equal(plan.dateWarn,3);
  assert.deepEqual(Array.from(plan.records,r=>[r.date,r.inspDate]),[['','2026-03-01'],['2026-04-01',''],['','']]);
  assert.equal(b.run('JSON.stringify(state)'),before);
  assert.equal(b.ctx._backupValidate([{date:'',supplier:'S'}]),null);
});
test('OCR only maps explicit incoming date and clears previous recognition date on failure',()=>{
  const b=browser();
  assert.equal(b.ctx.findDateNearKeyword('检验日期：2026-10-21\n送货日期：2026-10-20'),'');
  assert.equal(b.ctx.findDateNearKeyword('来料日期：\n检验日期：2026-10-21'),'');
  assert.equal(b.ctx.findDateNearKeyword('来料日期：\n2026-10-19'),'2026-10-19');
  assert.equal(b.ctx.findDateNearKeyword('来料日期：2026-02-30'),'');
  b.get('ocrDate').value='2026-10-19';b.ctx.extractFieldsFromOcrText('检验日期：2026-10-21');
  assert.equal(b.get('ocrDate').value,'');
});
test('server OCR rejects impossible and ambiguous date meanings',()=>{
  const source=fs.readFileSync(path.join(__dirname,'server/server.js'),'utf8');
  const context={};vm.createContext(context);vm.runInContext(functionSource(source,'parseDeliveryNote'),context);
  for(const text of ['检验日期：2026-10-19','送货日期：2026-10-19','日期：2026-10-19','2026年10月19日','来料日期：2026-02-30']) assert.equal(context.parseDeliveryNote(text).date,'');
  assert.equal(context.parseDeliveryNote('来料日期：2024-02-29').date,'2024-02-29');
});
test('inspection details mark missing fields without row tint, wrapping or invented zero values',()=>{
  const b=browser();b.run(`state={records:[{id:1,date:'2026-02-30',inspDate:'',supplier:'S',result:'PASS'}],nextId:2};can=()=>true;applyColLock=()=>{};_updateBatchBtn=()=>{};`);
  const before=b.run('JSON.stringify(state)');b.ctx.filterRecords();
  const html=b.get('recordsTableWrap').innerHTML;
  const doc=new (require('jsdom').JSDOM)(html).window.document;
  const row=doc.querySelector('tbody tr'),cells=row.querySelectorAll('td');
  assert.equal(row.classList.contains('qc-date-warning'),false);
  assert.equal(row.querySelector('.qc-date-warning-label'),null);
  assert.match(cells[2].textContent,/—/);assert.match(cells[2].querySelector('span').title,/客排期未提供计划验货日期/);
  assert.equal(cells[4].textContent,'S');assert.equal(cells[4].querySelector('.qc-missing-value'),null);
  assert.equal(cells[14].textContent,'—');assert.equal(cells[17].textContent,'PASS');
  assert.doesNotMatch(html,/2026-02-30/);
  assert.equal(b.ctx._recordFieldDisplay(0,'FAIL数'),0);
  assert.equal(b.ctx._recordFieldDisplay('0.00%','不良率'),'0.00%');
  assert.match(b.ctx._recordFieldDisplay('  ','PO号'),/qc-missing-value/);
  assert.equal(b.run('JSON.stringify(state)'),before);
});
test('date row warnings do not flag valid independent dates or change date semantics',()=>{
  const b=browser();const record={date:'2026-04-09',inspDate:'2026-04-07'};
  assert.equal(b.ctx._dateRowAttrs(record),'');assert.equal(record.inspDate,'2026-04-07');
});
function recordEntryBrowser() {
  const b=browser();b.run(`state={records:[],nextId:1};editingId=null;currentPage='test';_defectRows=[];_measRows=[];
    getSupplierOptions=()=>['S'];getCustomerOptions=()=>[];getProcessTypeOptions=()=>[];
    initDefectLib=()=>{};persist=()=>{};showToast=()=>{};closeModalDirect=()=>{};
    renderSupplierDatalist=()=>{};renderCustomerDatalist=()=>{};renderProcessTypeDatalist=()=>{};updateTopKpis=()=>{};`);
  b.get('f_supplier').value='S';b.get('f_result').value='PASS';return b;
}
for(const [arrival,inspection] of [['',''],['2026-10-19',''],['','2026-10-20']]) test('saving independently empty dates '+arrival+'/'+inspection,()=>{
  const b=recordEntryBrowser();b.ctx._setRecordDateInput('f_date',arrival);b.ctx._setRecordDateInput('f_inspDate',inspection);
  b.ctx.saveRecord();const r=JSON.parse(b.run('JSON.stringify(state.records[0])'));
  assert.equal(r.date,arrival);assert.equal(r.inspDate,inspection);assert.equal(r.status,'pending');
});
test('saving another field in an old record preserves its unrecognized date verbatim',()=>{
  const b=recordEntryBrowser();b.run(`state.records=[{id:1,date:'2026-02-30',inspDate:'not known',supplier:'S',result:'PASS',status:'pending'}];editingId=1;`);
  b.ctx._setRecordDateInput('f_date','2026-02-30',true);b.ctx._setRecordDateInput('f_inspDate','not known',true);
  b.get('f_remark').value='updated';b.ctx.saveRecord();const r=JSON.parse(b.run('JSON.stringify(state.records[0])'));
  assert.equal(r.date,'2026-02-30');assert.equal(r.inspDate,'not known');assert.equal(r.remark,'updated');
});
test('JSON import no longer copies arrival date into inspection date',()=>{
  const b=recordEntryBrowser();b.run('_backupLog=()=>{};_backupRefreshAll=()=>{}');
  b.ctx._backupDoImport([{date:'2026-10-19',supplier:'S'},{date:'invalid',inspDate:'2026-10-20',supplier:'S'}],'append');
  const records=JSON.parse(b.run('JSON.stringify(state.records)'));
  assert.deepEqual(records.map(r=>[r.date,r.inspDate]),[['2026-10-19',''],['','2026-10-20']]);
});
test('review center also marks missing dates without changing records',()=>{
  const b=browser();b.run(`state={records:[{id:1,date:null,inspDate:'invalid',supplier:'S',status:'pending',result:'PASS'}],nextId:2};can=()=>true;`);
  const before=b.run('JSON.stringify(state)');b.ctx.renderReviewPage();
  assert.match(b.get('reviewTableWrap').innerHTML,/qc-date-warning/);assert.doesNotMatch(b.get('reviewTableWrap').innerHTML,/invalid/);
  assert.equal(b.run('JSON.stringify(state)'),before);
});
test('untouched null and absent original date values retain their types',()=>{
  const b=browser();for(const raw of [null,undefined,'']) { b.ctx._setRecordDateInput('f_date',raw,true);assert.equal(b.ctx._recordDateValue('f_date'),raw); }
});
test('OCR preview applies manually supplied inspection date independently',()=>{
  const b=recordEntryBrowser();b.run('_syncOrderNoNA=()=>{};switchModalMode=()=>{}');
  b.get('ocrDate').value='2026-10-19';b.get('ocrInspDate').value='2026-10-20';b.ctx.applyOcrToForm();b.ctx.saveRecord();
  assert.equal(b.run('state.records[0].date'),'2026-10-19');assert.equal(b.run('state.records[0].inspDate'),'2026-10-20');
});
test('real AI multi-item wrapper preserves reviewed dates across successive queue items',async()=>{
  const b=recordEntryBrowser();b.ctx.fetch=async()=>({ok:true,json:async()=>({ready:false})});
  b.run(`openAddModal=()=>{_setRecordDateInput('f_date','');_setRecordDateInput('f_inspDate','');editingId=null;};onQtyChange=()=>{};onProductNoChange=()=>{};`);
  b.get('modalOverlay').classList.contains=()=>false;
  vm.runInContext(fs.readFileSync(path.join(__dirname,'ai-ocr.js'),'utf8'),b.ctx);
  b.ctx.__qcAiResult={common:{date:'2026-02-30',supplier:'S'},items:[{productNo:'P1',qty:0},{productNo:'P2',qty:0}]};
  b.get('ocrDate').value='2026-10-19';b.get('ocrInspDate').value='2026-10-20';b.ctx.applyOcrToForm();
  for(let i=0;i<2;i++){
    assert.equal(b.get('f_date').value,'2026-10-19');assert.equal(b.get('f_inspDate').value,'2026-10-20');b.ctx.saveRecord();
  }
  const rows=JSON.parse(b.run('JSON.stringify(state.records)'));
  assert.equal(rows.length,2);assert.ok(rows.every(r=>r.date==='2026-10-19'&&r.inspDate==='2026-10-20'));await Promise.resolve();
});
if(process.env.QC_READONLY_RECORDS && process.env.QC_BASELINE_DIR) test('read-only actual records retain all chart data and date selections versus pre-change source',()=>{
  const rows=JSON.parse(fs.readFileSync(process.env.QC_READONLY_RECORDS,'utf8'));
  for(const r of rows) for(const key of ['defects','measurements']) if(typeof r[key]==='string') r[key]=JSON.parse(r[key]||'[]');
  const baseline=browser(fs.readFileSync(path.join(process.env.QC_BASELINE_DIR,'app.js'),'utf8'),fs.readFileSync(path.join(process.env.QC_BASELINE_DIR,'report_export.js'),'utf8'));
  const updated=browser();const outputs=[];
  for(const b of [baseline,updated]){
    b.ctx.actualRows=structuredClone(rows);b.run('state={records:actualRows,nextId:31};getCompanyName=()=>"华兴";');
    const charts={};b.ctx.makeChart=id=>({setOption:option=>charts[id]=JSON.parse(JSON.stringify(option))});
    b.ctx.getComputedStyle=()=>({getPropertyValue:()=>''});b.ctx.document.body={classList:{contains:()=>false}};
    for(const name of ['chartDailyTrend','chartResultPie','chartSupplierRank','chartDefectTop','chartClientPie','chartWeeklyTrend','chartWeeklySupplier','chartProductType','chartFailMonth','chartDefectHeatmap']) b.ctx[name](b.ctx.actualRows);
    const periods=['2026-03-31','2026-04-01','2026-04-07','2026-04-09'].map(day=>b.run(`recs().filter(r=>r.date==='${day}'||r.inspDate==='${day}').map(r=>r.id).join(',')`));
    const weeks=['2026-03-30','2026-04-06'].map(day=>b.run(`recs().filter(r=>r.date>='${day}'&&r.date<=weekEnd('${day}')).map(r=>r.id).join(',')`));
    outputs.push({charts,periods,weeks,rows:JSON.parse(b.run('JSON.stringify(state.records)'))});
  }
  assert.deepEqual(outputs[1],outputs[0]);assert.equal(rows.length,30);assert.equal(rows.reduce((s,r)=>s+Number(r.qty||0),0),60413);
});


test('authoritative refresh preserves another account inspector on the next save',async()=>{
 const b=browser();
 b.run(`state={records:[{id:31,qc:'历史姓名'}],nextId:78};window.__QC_KNOWN_RECORD_IDS=new Set([31]);window.__QC_NEXUS.inspector={id:'current',name:'当前账号'};getCompany=()=> 'hy-huaxing';filterRecords=()=>{};updateTopKpis=()=>{};showToast=()=>{};`);
 b.ctx.confirm=()=>true;
 b.ctx.fetch=async()=>({ok:true,json:async()=>({records:[{id:31,qc:'历史姓名'},{id:78,qc:'另一账号'}],nextId:79})});
 await b.ctx.refreshRecordsPage();
 b.run('persist()');
 assert.equal(b.run('state.records[1].qc'),'另一账号');
 assert.equal(b.run('window.__QC_KNOWN_RECORD_IDS.has(78)'),true);
});
