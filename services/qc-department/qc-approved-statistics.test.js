'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const tick=()=>new Promise(r=>setTimeout(r,5));
function page(){
  const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),{runScripts:'outside-only',url:'http://localhost/'});
  const w=dom.window,d=w.document,calls=[];
  const add=d.addEventListener.bind(d);d.addEventListener=(name,...args)=>{if(name!=='DOMContentLoaded')add(name,...args);};
  const menus=()=>Array.from(d.querySelectorAll('#sidebar [data-page]'),x=>[x.dataset.page,x.textContent.trim(),x.getAttribute('onclick'),x.style.display]);
  const originalMenus=menus();
  w.__QC_NEXUS={factory:'huaxing',exportAllowed:true};
  w.eval(fs.readFileSync(path.join(__dirname,'app.js'),'utf8'));
  w._saveSession({username:'test-admin',role:'admin'});
  w.eval(fs.readFileSync(path.join(__dirname,'qc-approved-statistics.js'),'utf8'));
  d.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));d.getElementById('page-analysis').classList.add('active');w.eval("currentPage='analysis'");
  const data={factory:'huaxing',source:'current-inline-approved-summary-v1',ready:true,
    filters:{year:'2026',month:'',day:'',customer:'',result:'FAIL'},
    options:{years:['2026','2025'],months:['11'],days:[],customers:[{key:'a'.repeat(64),label:'客户 <img src=x onerror=alert(1)> · A'}]},
    totals:{total:4,PASS:1,FAIL:1,PENDING:1,LG:1,decided:2,other:{},passRate:50},
    months:[{month:'2026-11',total:4,PASS:1,FAIL:1,PENDING:1,LG:1,other:{},passRate:50}],
    details:{items:[{id:'1',date:'2026-11-03',customer:'客户甲',poNo:'PO-1',productName:'<script>bad</script>',result:'FAIL',remark:'刮花\n待复核'}],total:1,page:1,pageSize:5,pages:1},
    excluded:{},missingDate:0,notices:[]};
  w.fetch=async(url,opts)=>{calls.push({url,opts});const result=structuredClone(data),q=new URL(url,'http://localhost').searchParams;for(const k of Object.keys(result.filters))if(q.has(k))result.filters[k]=q.get(k);return{ok:true,json:async()=>result};};
  return{dom,w,d,calls,data,menus,originalMenus,el:n=>d.getElementById('qstats-'+n)};
}
test('real report source renders approved design and preserves every sidebar entry',async()=>{
  const p=page();try{
    await p.w.renderAnalysis();assert.match(p.calls[0].url,/^api\/approved-statistics\/report\?/);assert.equal(p.calls[0].opts.cache,'no-store');
    assert.equal(p.el('total').textContent,'4');assert.equal(p.el('rate').textContent,'50.0%');
    assert.equal(p.el('month-rows').children.length,12);assert.equal(p.el('bars').children.length,12);
    assert.equal(p.el('bars').children[10].querySelector('.qc-bar-fill').dataset.band,'red');
    assert.equal(p.d.getElementById('chartProductType'),null);
    assert.equal(p.el('client').querySelector('img'),null);assert.equal(p.el('detail-rows').querySelector('script'),null);
    assert.match(p.el('detail-rows').textContent,/<script>bad<\/script>/);
    p.data.scheduleDateCount=1;p.data.details.items[0].usesScheduleDate=true;
    await p.w.renderAnalysis();
    assert.equal(p.el('message').textContent,'');
    assert.equal(p.el('scope'),null);
    assert.equal(p.el('detail-rows').querySelector('td').textContent,'2026-11-03（排期）');
    assert.deepEqual(p.menus(),p.originalMenus);assert.equal(p.d.querySelectorAll('.qstats-brand').length,0);
    p.w.applyTheme('dark');assert.equal(p.el('rate').textContent,'50.0%');
    p.w.QcApprovedStatistics.pageChanged('daily');assert(!p.d.body.classList.contains('qc-approved-analysis'));
  }finally{p.dom.window.close();}
});
test('report center defaults to weekly and switches reports even while annual data is loading',async()=>{
  const p=page();try{
    const frameQueue=[];
    p.w.requestAnimationFrame=callback=>frameQueue.push(callback);
    p.w.renderWeeklyReport=()=>{};
    p.w.renderDailyReport=()=>{};
    p.w.renderMonthlyReport=()=>{};
    const flush=()=>{while(frameQueue.length)frameQueue.shift()();};
    const select=p.d.getElementById('reportTypeSelect');
    const nav=p.d.querySelector('#sidebar [data-page="report-center"]');
    assert.equal(nav.textContent.trim(),'报告中心');
    assert.equal(p.d.querySelectorAll('#sidebar [data-page]:is([data-page="daily"],[data-page="weekly"],[data-page="monthly"],[data-page="yearly"],[data-page="analysis"])').length,0);
    p.w.showPage('report-center');flush();
    assert.equal(select.value,'weekly');
    assert.equal(select.closest('.page.active').id,'page-weekly');
    assert(nav.classList.contains('active'));
    p.w.fetch=()=>new Promise(()=>{});
    for(const key of ['daily','monthly','analysis','weekly']){
      select.value=key;
      p.w.changeReportType(select);flush();
      assert.equal(select.value,key);
      assert.equal(select.closest('.page.active').id,'page-'+key);
      assert.equal(p.d.activeElement,select);
      assert(!select.disabled);
    }
    p.w._saveUsers([{username:'test-admin',role:'admin',perms:{weekly:{v:0},monthly:{v:0},analysis:{v:0}}}]);
    p.w.showPage('report-center');flush();
    assert.equal(select.value,'daily');
    assert.deepEqual(Array.from(select.options).filter(option=>!option.disabled).map(option=>option.value),['daily']);
  }finally{p.dom.window.close();}
});
test('five colors use exact boundaries; null stays blank and true zero stays red',async()=>{
  const p=page();try{
    for(const [rate,key] of [[100,'green'],[90,'green'],[89.999,'yellow-light'],[80,'yellow-light'],[79.999,'yellow-deep'],[70,'yellow-deep'],[69.999,'red-light'],[60,'red-light'],[59.999,'red'],[0,'red']])assert.equal(p.w.QcApprovedStatistics.rateBand(rate).key,key);
    assert.equal(p.w.QcApprovedStatistics.rateBand(null),null);
    p.data.months[0].passRate=0;await p.w.renderAnalysis();
    const fill=p.el('bars').children[10].querySelector('.qc-bar-fill');assert.equal(fill.dataset.band,'red');assert.equal(fill.textContent,'0.0%');
    p.data.months[0].passRate=null;p.data.totals.passRate=null;await p.w.renderAnalysis();
    assert.equal(fill.dataset.band,'empty');assert.equal(fill.textContent,'');assert.equal(p.el('rate').textContent,'—');
  }finally{p.dom.window.close();}
});
test('data-only cascading selects update immediately, month table and chart are clickable',async()=>{
  const p=page();try{
    await p.w.renderAnalysis();assert.deepEqual(Array.from(p.el('month').options,o=>o.value),['','11']);assert(p.el('day').disabled);
    p.data.options.days=['3'];p.el('month').value='11';p.el('month').dispatchEvent(new p.w.Event('change'));await tick();
    assert.match(p.calls.at(-1).url,/month=11/);assert.deepEqual(Array.from(p.el('day').options,o=>o.value),['','3']);assert(!p.el('day').disabled);
    p.el('day').value='3';p.el('day').dispatchEvent(new p.w.Event('change'));await tick();assert.match(p.calls.at(-1).url,/day=3/);
    p.el('client').value='a'.repeat(64);p.el('client').dispatchEvent(new p.w.Event('change'));await tick();assert.match(p.calls.at(-1).url,/customer=a+/);
    p.el('year').value='2025';p.el('year').dispatchEvent(new p.w.Event('change'));await tick();assert.match(p.calls.at(-1).url,/year=2025/);assert.doesNotMatch(p.calls.at(-1).url,/month=|day=/);
    p.el('reset').click();await tick();assert.doesNotMatch(p.calls.at(-1).url,/year=|customer=/);
    p.el('month-rows').children[10].querySelector('button').click();await tick();assert.match(p.calls.at(-1).url,/month=11/);
    p.el('bars').children[10].querySelector('button').click();await tick();assert.doesNotMatch(p.calls.at(-1).url,/month=/);
  }finally{p.dom.window.close();}
});
test('result tabs and pagination request details without altering aggregate values',async()=>{
  const p=page();try{
    p.data.details.total=12;p.data.details.pages=3;await p.w.renderAnalysis();
    p.el('root').querySelector('[data-result="PENDING"]').click();await tick();assert.match(p.calls.at(-1).url,/result=PENDING/);
    p.el('next').click();await tick();assert.match(p.calls.at(-1).url,/page=2/);assert.equal(p.el('total').textContent,'4');
  }finally{p.dom.window.close();}
});
test('empty report and missing dates stay explicit; errors never leave stale figures',async()=>{
  const p=page();try{
    p.data.options={years:[],months:[],days:[],customers:[]};p.data.filters.year='';p.data.months=[];p.data.details.items=[];p.data.details.total=0;p.data.totals={total:0,PASS:0,FAIL:0,PENDING:0,LG:0,decided:0,other:{},passRate:null};p.data.missingDate=1;
    await p.w.renderAnalysis();assert(p.el('year').disabled);assert.equal(p.el('rate').textContent,'—');assert.match(p.el('message').textContent,/未填写最终验货日期/);assert.match(p.el('detail-rows').textContent,/暂无此类记录/);
    p.w.fetch=async()=>({ok:false,json:async()=>({detail:'权限变化'})});await p.w.renderAnalysis();assert.equal(p.el('total').textContent,'—');assert.equal(p.el('detail-rows').children.length,0);assert.match(p.el('message').textContent,/权限变化/);assert(!p.el('refresh').disabled);
    p.w.fetch=async()=>({ok:true,json:async()=>({...p.data,factory:'huadeng'})});await p.w.renderAnalysis();assert.match(p.el('message').textContent,/厂区不一致/);
  }finally{p.dom.window.close();}
});
test('late responses and leaving page cannot overwrite a newer selection',async()=>{
  const p=page();try{
    let resolve;p.w.fetch=()=>new Promise(r=>{resolve=r;});const pending=p.w.renderAnalysis();
    p.w.QcApprovedStatistics.pageChanged('review');resolve({ok:true,json:async()=>p.data});await pending;assert.equal(p.el('total').textContent,'—');
    delete p.w.__QC_NEXUS;const before=p.calls.length;await p.w.QcApprovedStatistics.load();assert.equal(p.calls.length,before);
  }finally{p.dom.window.close();}
});
