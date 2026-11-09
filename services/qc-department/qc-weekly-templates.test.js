'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const templates=JSON.parse(fs.readFileSync(path.join(__dirname,'../../backend/app/templates/qc-weekly/templates.json'),'utf8'));
const key='a'.repeat(64), fields=['returns','returnReason','hongKongContact','weeklyRemark','reworkA0D','handling'];
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
function fixture(n=3){return {date:'2026-11-05',dateFrom:'2026-11-02',dateTo:'2026-11-08',sourceRevision:'b'.repeat(64),templates,canEdit:true,canExport:true,total:n,scheduleCount:0,
  customers:[{key,name:'合成客户',label:'合成客户 · A'}],fields:{[key]:Object.fromEntries(fields.map(f=>[f,{value:'',version:0}]))},
  tables:{detail:Array.from({length:n},(_,i)=>({id:'entry-'+i,customerKey:key,dateSource:'qc_manual',values:[i+1,'2026-11-05','合成客户','001','UK','SKU','产品',100,'10','10','FAIL','有','生产部','机构','问题','负责人一','负责人二','原备注']})),
    group:[{id:key,values:['华兴','合成客户',n,'','','','','']}],internal:[{id:key,values:['合成客户',n,'','','','负责人一 / 负责人二','','']}],footer:[{id:key,values:['华兴','合成客户',n,'','','','','','']}]}};}
function page(options={}){
  const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),{url:'http://localhost/api/qc-department/huaxing/u-test/',runScripts:'outside-only'}),w=dom.window,d=w.document;
  w.__QC_NEXUS={factory:options.factory||'huaxing'};d.getElementById('weeklyDate').value='2026-11-05';
  let data=fixture(options.n);const calls=[];
  const response=(value,status=200)=>({ok:status===200,status,json:async()=>JSON.parse(JSON.stringify(value))});
  w.fetch=async(url,init)=>{
    calls.push({url,init});if(!init.body)return response(data);
    const body=JSON.parse(init.body);data.fields[body.customerKey][body.field]={value:body.value,version:body.baseVersion+1};
    return response({...body,version:body.baseVersion+1});
  };
  if(options.storage)for(const [k,v]of Object.entries(options.storage))w.localStorage.setItem(k,v);
  w.eval(fs.readFileSync(path.join(__dirname,'qc-weekly-templates.js'),'utf8'));d.dispatchEvent(new w.Event('DOMContentLoaded'));
  const edit=(field,value)=>{d.querySelector('[data-field="'+field+'"]').click();const input=d.querySelector('.qwt-editor');input.value=value;input.dispatchEvent(new w.Event('input',{bubbles:true}));return input;};
  return {dom,w,d,calls,data,response,edit};
}

test('all original columns, dynamic rows, two totals, independent cells and locked source',async()=>{
  const p=page({n:220});try{
    assert.equal(p.d.querySelectorAll('#qwtEntries button').length,3);
    await p.w.QcWeeklyTemplates.open('detail');
    assert.equal(p.d.querySelectorAll('#qwtTables table')[0].querySelectorAll('tbody tr').length,220);
    assert.equal(p.d.querySelectorAll('#qwtTables table')[0].querySelectorAll('.qwt-cell').length,0);
    assert.equal(p.d.querySelectorAll('#qwtTables [colspan],#qwtTables [rowspan]').length,0);
    for(const kind of ['group','internal']){
      await p.w.QcWeeklyTemplates.open(kind);
      assert.equal(p.d.querySelectorAll('tfoot td').length,8);
      assert.match(p.d.querySelector('tfoot').textContent,/合计220待补全/);
    }
    assert.equal(p.d.querySelector('[data-field="firstResponsible"]'),null);
  }finally{p.dom.window.close();}
});

test('existing week control returns without a back button, protects drafts and cancels late loads',async()=>{
  const p=page();try{
    const source=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
    p.w.eval('var currentPage="weekly";'+source.slice(source.indexOf('function changeReportPeriod('),source.indexOf('function changeReportType(')));
    const week=p.d.querySelector('[data-report-page="weekly"]');
    await p.w.QcWeeklyTemplates.open('group');
    assert.equal(p.d.getElementById('qwtBack'),null);
    p.edit('returns','1');p.w.changeReportPeriod(week);
    assert.equal(p.d.getElementById('qwtView').hidden,false);
    await p.w.QcWeeklyTemplates.flush();p.w.changeReportPeriod(week);
    assert.equal(p.d.getElementById('qwtView').hidden,true);
    assert.equal(p.d.getElementById('weeklyReportBody').hidden,false);
    p.w.QcWeeklyTemplates.pageChanged('daily');
    let resolve;p.w.fetch=()=>new Promise(r=>resolve=r);
    const loading=p.w.QcWeeklyTemplates.open('internal');p.w.changeReportPeriod(week);
    resolve(p.response(p.data));await loading;
    assert.equal(p.d.getElementById('qwtView').hidden,true);
    p.w.fetch=async()=>{throw Error('读取失败');};await p.w.QcWeeklyTemplates.open('detail');
    assert.equal(p.d.getElementById('qwtBack'),null);p.w.changeReportPeriod(week);
    assert.equal(p.d.getElementById('weeklyReportBody').hidden,false);
  }finally{p.dom.window.close();}
});

test('fast edits serialize with updated versions and share values across templates',async()=>{
  const p=page();try{
    await p.w.QcWeeklyTemplates.open('group');
    const deferred=[];p.w.fetch=(url,init)=>new Promise(resolve=>deferred.push({resolve,body:JSON.parse(init.body)}));
    const input=p.edit('weeklyRemark','第一版');const saving=p.w.QcWeeklyTemplates.flush();
    input.value='第二版';input.dispatchEvent(new p.w.Event('input',{bubbles:true}));
    assert.equal(deferred.length,1);deferred[0].resolve(p.response({...deferred[0].body,version:1}));await tick();
    assert.equal(deferred.length,2);assert.equal(deferred[1].body.value,'第二版');assert.equal(deferred[1].body.baseVersion,1);
    deferred[1].resolve(p.response({...deferred[1].body,version:2}));await saving;
    assert.equal(p.w.QcWeeklyTemplates.navigationState().dirty,false);
    await p.w.QcWeeklyTemplates.open('internal');
    assert.equal(p.d.querySelector('[data-field="weeklyRemark"]').textContent,'第二版');
    assert.equal(p.w.localStorage.length,0);
  }finally{p.dom.window.close();}
});

test('unknown network outcome retains exact idempotency key; reload restores draft',async()=>{
  const p=page();let storage;try{
    await p.w.QcWeeklyTemplates.open('group');p.edit('returns','1');
    let first;p.w.fetch=async(url,init)=>{first=JSON.parse(init.body);throw Error('网络断开');};
    await p.w.QcWeeklyTemplates.flush();
    assert.match(p.d.getElementById('qwtStatus').textContent,/网络断开/);
    const date=p.d.getElementById('weeklyDate');date.value='2026-12-01';date.dispatchEvent(new p.w.Event('change',{bubbles:true}));assert.equal(date.value,'2026-11-05');
    storage=Object.fromEntries(Object.keys(p.w.localStorage).map(k=>[k,p.w.localStorage.getItem(k)]));
    const q=page({storage});try{
      await q.w.QcWeeklyTemplates.open('group');
      assert.equal(q.d.querySelector('[data-field="returns"]').textContent,'1');
      let retry;q.w.fetch=async(url,init)=>{retry=JSON.parse(init.body);return q.response({...retry,version:1});};
      q.d.getElementById('qwtRetry').click();await tick();
      assert.deepEqual(retry,first);assert.equal(q.w.QcWeeklyTemplates.navigationState().dirty,false);
      assert.match(q.d.querySelector('tfoot').textContent,/33.3%/);
    }finally{q.dom.window.close();}
  }finally{p.dom.window.close();}
});

test('conflicts require explicit choice and never overwrite another editor silently',async()=>{
  const p=page();try{
    await p.w.QcWeeklyTemplates.open('internal');p.edit('handling','我的处理');
    p.w.fetch=async()=>p.response({detail:{code:'cell_conflict',message:'冲突',current:{value:'别人处理',version:3}}},409);
    await p.w.QcWeeklyTemplates.flush();assert.match(p.d.getElementById('qwtConflict').textContent,/别人处理/);
    let request;p.w.fetch=async(url,init)=>{request=JSON.parse(init.body);return p.response({...request,version:4});};
    p.d.getElementById('qwtKeepDraft').click();await tick();
    assert.equal(request.baseVersion,3);assert.equal(request.value,'我的处理');assert.equal(p.w.QcWeeklyTemplates.navigationState().dirty,false);
  }finally{p.dom.window.close();}
});

test('read failures clear visible table, read-only permission, empty records and other factories',async()=>{
  const p=page();try{
    p.data.canEdit=false;await p.w.QcWeeklyTemplates.open('group');assert.equal(p.d.querySelectorAll('.qwt-cell').length,0);
    p.w.fetch=async()=>{throw Error('无法读取');};p.d.getElementById('qwtRefresh').click();await tick();
    assert.equal(p.d.querySelector('#qwtView table'),null);assert.match(p.d.getElementById('qwtView').textContent,/无法读取/);
  }finally{p.dom.window.close();}
  const q=page({factory:'huadeng'});try{await q.w.QcWeeklyTemplates.open('group');assert.equal(q.calls.length,0);assert.equal(q.d.getElementById('qwtEntries').hidden,true);}finally{q.dom.window.close();}
  const r=page({n:0});try{r.data.tables={detail:[],group:[],internal:[],footer:[]};await r.w.QcWeeklyTemplates.open('group');assert.match(r.d.getElementById('qwtView').textContent,/没有已审核/);assert.equal(r.d.querySelectorAll('tfoot td').length,8);}finally{r.dom.window.close();}
});

test('Tab starts inline editing, Escape restores text, and source refresh compares pending versions',async()=>{
  const p=page();try{
    await p.w.QcWeeklyTemplates.open('group');
    const input=p.edit('returns','1');input.dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));
    assert.equal(p.d.querySelector('.qwt-editor').getAttribute('aria-label'),'合成客户 退货原因');
    let current=p.d.querySelector('.qwt-editor');current.value='撤销内容';current.dispatchEvent(new p.w.Event('input',{bubbles:true}));
    current.dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
    assert.equal(p.d.querySelector('[data-field="returnReason"]').textContent,'');
    p.w.fetch=async()=>p.response({detail:{code:'source_changed',message:'来源变动'}},409);
    await p.w.QcWeeklyTemplates.flush();assert.match(p.d.getElementById('qwtConflict').textContent,/来源变动/);
    p.data.sourceRevision='c'.repeat(64);p.data.fields[key].returns={value:'2',version:2};
    p.w.fetch=async()=>p.response(p.data);
    p.d.getElementById('qwtCompare').click();await tick();
    assert.equal(p.d.querySelector('[data-field="returns"]').textContent,'1');
    p.d.getElementById('qwtRetry').click();await tick();
    assert.match(p.d.getElementById('qwtConflict').textContent,/服务器：2/);
    p.d.getElementById('qwtUseServer').click();await tick();
    assert.equal(p.d.querySelector('[data-field="returns"]').textContent,'2');assert.equal(p.w.QcWeeklyTemplates.navigationState().dirty,false);
  }finally{p.dom.window.close();}
});

test('all allowed empty supplements normalize missing/null values and persist across three templates',async()=>{
  const p=page();try{
    p.data.fields[key]={returns:{value:null,version:0},returnReason:null,weeklyRemark:{value:undefined,version:0}};
    const groups={detail:['returns','returnReason','hongKongContact','reworkA0D','weeklyRemark'],group:['returns','returnReason','hongKongContact','weeklyRemark'],internal:['returns','returnReason','handling','weeklyRemark']};
    for(const [kind,allowed]of Object.entries(groups)){
      await p.w.QcWeeklyTemplates.open(kind);
      for(const field of allowed){p.edit(field,field==='returns'?'0':kind+'已补充');await p.w.QcWeeklyTemplates.flush();}
      assert.equal(p.w.QcWeeklyTemplates.navigationState().dirty,false);
    }
    await p.w.QcWeeklyTemplates.open('detail');
    assert.equal(p.d.querySelector('[data-field="returns"]').textContent,'0');
    assert.equal(p.d.querySelector('[data-field="weeklyRemark"]').textContent,'internal已补充');
    p.d.querySelector('.qwt-cell').click();p.d.querySelector('.qwt-editor').dispatchEvent(new p.w.Event('blur'));
    p.d.getElementById('qwtRefresh').click();await tick();
    assert.equal(p.d.querySelector('[data-field="weeklyRemark"]').textContent,'internal已补充');
  }finally{p.dom.window.close();}
});

test('template width is scoped; Excel exports selected template, saved versions and customer only',async()=>{
  const p=page();try{
    const captures=[];let link;
    p.d.addEventListener('click',e=>{if(e.target.tagName==='A'){link={url:e.target.getAttribute('href'),name:e.target.download};e.preventDefault();}},true);
    const original=p.w.fetch;
    p.w.fetch=async(url,init)=>{if(url.endsWith('/excel')){captures.push(JSON.parse(init.body));return p.response({url:'api/weekly-templates/excel/abc123.token',filename:'表格.xls'});}return original(url,init);};
    for(const kind of ['detail','group','internal']){
      await p.w.QcWeeklyTemplates.open(kind);
      assert(p.d.getElementById('weeklyReportContent').classList.contains('qwt-open'));
      p.d.getElementById('qwtExcel').click();await tick();
      assert.equal(captures.at(-1).template,kind);assert.equal('paper' in captures.at(-1),false);
      assert.deepEqual(captures.at(-1).versions,{[key]:Object.fromEntries(fields.map(f=>[f,0]))});
      assert.equal(link.url,'api/weekly-templates/excel/abc123.token');
      p.w.QcWeeklyTemplates.returnToReport();assert(!p.d.getElementById('weeklyReportContent').classList.contains('qwt-open'));
    }
    await p.w.QcWeeklyTemplates.open('internal');
    const customer=p.d.getElementById('qwtCustomer');customer.value=key;customer.dispatchEvent(new p.w.Event('change'));await tick();
    p.d.getElementById('qwtExcel').click();await tick();assert.equal(captures.at(-1).customer,key);
    p.edit('handling','待保存');assert.equal(p.d.getElementById('qwtExcel').disabled,true);
    await p.w.QcWeeklyTemplates.flush();
    p.w.fetch=async()=>p.response({detail:'记录已变化'},409);
    p.d.getElementById('qwtExcel').click();await tick();assert.match(p.d.getElementById('qwtExcelStatus').textContent,/Excel 导出失败：记录已变化/);
  }finally{p.dom.window.close();}
});

test('blank detail cells are editable per entry and reload their saved value',async()=>{
  const p=page();try{
    const [first,second]=p.data.tables.detail;
    const a='detail:'+first.id+':contractNo', b='detail:'+second.id+':contractNo';
    for(const [row,field]of [[first,a],[second,b]]){
      row.values[3]='';row.editableFields={3:field};
      p.data.fields[key][field]={value:'',version:0};
    }
    await p.w.QcWeeklyTemplates.open('detail');
    p.edit(a,'000123');
    await p.w.QcWeeklyTemplates.flush();
    const input=p.d.querySelector('.qwt-editor');
    input.dispatchEvent(new p.w.Event('blur'));
    p.d.getElementById('qwtRefresh').click();
    await tick();
    assert.equal(p.d.querySelector('[data-field="'+a+'"]').textContent,'000123');
    assert.equal(p.d.querySelector('[data-field="'+b+'"]').textContent,'');
    assert.equal(p.d.querySelectorAll('#qwtTables table:first-of-type tbody tr:first-child td')[5].textContent,'SKU');
  }finally{p.dom.window.close();}
});
